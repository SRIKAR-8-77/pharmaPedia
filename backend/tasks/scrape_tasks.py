import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from celery import shared_task
from sqlalchemy import select, and_

from tasks.celery_app import celery_app
from models.database import AsyncSessionLocal, Project, SourceLatency, GlobalSource, ProjectGlobalSource
from models.crud import bulk_insert_raw_posts, update_global_source_stats

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from within a sync Celery task."""
    from models.database import engine
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        # Dispose the async engine pool so connections don't leak across loops.
        # asyncpg connections are bound to the event loop that created them;
        # without dispose() the next call inherits stale connections.
        try:
            loop.run_until_complete(engine.dispose())
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)


async def _scrape_global_source_for_keyword(
    global_source: GlobalSource,
    keyword: str,
    project_id: UUID,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> int:
    """Fetch posts from a global source for one keyword and bulk-insert scoped to a project."""
    from scrapers.registry import get_scraper
    config = dict(global_source.scraper_config or {})
    if global_source.feed_url and "{keyword}" in global_source.feed_url:
        from urllib.parse import quote_plus
        config.setdefault("feed_urls", [global_source.feed_url.replace("{keyword}", quote_plus(keyword))])
    elif global_source.feed_url:
        config.setdefault("feed_urls", [global_source.feed_url])

    try:
        scraper = get_scraper(global_source.source_type, config)
    except Exception as e:
        logger.error(f"No scraper for global source {global_source.source_type}: {e}")
        return 0

    try:
        posts = await scraper.fetch(keyword, limit=100, since=since, until=until)
    except Exception as e:
        logger.error(f"Global source {global_source.name} fetch failed (keyword={keyword}): {e}")
        return 0

    if not posts:
        return 0

    rows = [
        {
            "project_id": project_id,
            "source": (p.source or "")[:50],
            "source_config_id": None,
            "keyword": (p.keyword or "")[:255],
            "text": p.text,
            "title": p.title,
            "author": (p.author or "")[:255] if p.author else None,
            "url": p.url,
            "external_id": (p.external_id or "")[:255] if p.external_id else None,
            "upvotes": p.upvotes,
            "comment_count": p.comment_count,
            "timestamp": p.timestamp,
            "processed": False,
        }
        for p in posts
    ]

    async with AsyncSessionLocal() as db:
        count = await bulk_insert_raw_posts(db, rows)
        await update_global_source_stats(db, global_source.id, count)
        await db.commit()

    return count


async def _run_global_sources_by_latency(latency: SourceLatency):
    """Scrape all global sources for all live (ongoing) projects at the given latency tier."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(GlobalSource, ProjectGlobalSource.keyword, ProjectGlobalSource.project_id,
                   GlobalSource.last_successful_run)
            .join(ProjectGlobalSource, ProjectGlobalSource.global_source_id == GlobalSource.id)
            .join(Project, Project.id == ProjectGlobalSource.project_id)
            .where(and_(
                ProjectGlobalSource.latency == latency,
                ProjectGlobalSource.enabled == True,
                GlobalSource.is_active == True,
                Project.is_active == True,
                # Only live/ongoing projects (date_to null or in the future)
                Project.date_to == None,
            ))
        )
        rows = result.all()

    for global_source, keyword, project_id, last_run in rows:
        since = last_run if last_run else None
        count = await _scrape_global_source_for_keyword(global_source, keyword, project_id, since=since)
        if count > 0:
            logger.info(f"Global scrape: {count} posts from {global_source.name} (keyword={keyword})")


@celery_app.task(name="tasks.scrape_tasks.run_realtime_sources", bind=True, max_retries=3)
def run_realtime_sources(self):
    try:
        _run_async(_run_global_sources_by_latency(SourceLatency.realtime))
    except Exception as exc:
        logger.error(f"run_realtime_sources failed: {exc}")
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="tasks.scrape_tasks.run_daily_sources", bind=True, max_retries=3)
def run_daily_sources(self):
    try:
        _run_async(_run_global_sources_by_latency(SourceLatency.daily))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="tasks.scrape_tasks.run_weekly_sources", bind=True, max_retries=3)
def run_weekly_sources(self):
    try:
        _run_async(_run_global_sources_by_latency(SourceLatency.weekly))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(name="tasks.scrape_tasks.run_batch_scrape_for_project")
def run_batch_scrape_for_project(project_id: str):
    """
    One-shot historical batch scrape for a project with date_from set.
    Only queries global sources with supports_date_range=True (FAERS, PubMed, Google News, Reddit).
    Fetches data from date_from to date_to (or now if date_to is null).
    """
    async def _run():
        pid = UUID(project_id)
        async with AsyncSessionLocal() as db:
            project = await db.get(Project, pid)
            if not project or not project.date_from:
                return

            since = project.date_from
            until = project.date_to  # None means fetch up to now

            from models.crud import get_project_global_source_configs
            global_configs = await get_project_global_source_configs(db, pid, date_range_only=True)

        total = 0
        for global_source, keyword, latency in global_configs:
            count = await _scrape_global_source_for_keyword(
                global_source, keyword, pid, since=since, until=until
            )
            total += count
            if count > 0:
                logger.info(f"Batch global scrape: {count} posts from {global_source.name} (keyword={keyword})")

        logger.info(f"Batch scrape complete for project {project_id[:8]}: {total} total posts ingested")

    _run_async(_run())


@celery_app.task(name="tasks.scrape_tasks.scrape_project_now")
def scrape_project_now(project_id: str):
    """On-demand scrape triggered via API — runs all active global sources for the project."""
    async def _run():
        pid = UUID(project_id)
        async with AsyncSessionLocal() as db:
            project = await db.get(Project, pid)
            if not project:
                return

            from models.crud import get_project_global_source_configs
            global_configs = await get_project_global_source_configs(db, pid)

        for global_source, keyword, latency in global_configs:
            count = await _scrape_global_source_for_keyword(global_source, keyword, pid)
            if count > 0:
                logger.info(f"On-demand global scrape: {count} posts from {global_source.name} (keyword={keyword})")

    _run_async(_run())
