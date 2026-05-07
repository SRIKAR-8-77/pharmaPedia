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
from scrapers.registry import get_scraper

logger = logging.getLogger(__name__)


from dataclasses import dataclass

@dataclass
class _GSProxy:
    """Plain-data stand-in for a GlobalSource row — safe to use after the DB session closes."""
    id: object
    name: str
    source_type: str
    url: str
    feed_url: object
    scraper_config: dict
    last_successful_run: object
    is_active: bool


def _make_gs(gs_id, name, source_type, url, feed_url, scraper_config, last_run, is_active):
    return _GSProxy(
        id=gs_id, name=name, source_type=source_type, url=url,
        feed_url=feed_url, scraper_config=scraper_config or {},
        last_successful_run=last_run, is_active=is_active,
    )


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
            select(GlobalSource, ProjectGlobalSource.keyword, ProjectGlobalSource.project_id)
            .join(ProjectGlobalSource, ProjectGlobalSource.global_source_id == GlobalSource.id)
            .join(Project, Project.id == ProjectGlobalSource.project_id)
            .where(and_(
                ProjectGlobalSource.latency == latency,
                ProjectGlobalSource.enabled == True,
                GlobalSource.is_active == True,
                Project.is_active == True,
                Project.is_paused == False,
                Project.date_to == None,
            ))
        )
        rows = result.all()
        # Extract all attributes while session is still open
        configs = [
            (gs.id, gs.name, gs.source_type, gs.url, gs.feed_url,
             gs.scraper_config, gs.last_successful_run, gs.is_active, keyword, project_id)
            for gs, keyword, project_id in rows
        ]

    for (gs_id, gs_name, gs_type, gs_url, gs_feed, gs_cfg,
         last_run, is_active, keyword, project_id) in configs:
        gs = _make_gs(gs_id, gs_name, gs_type, gs_url, gs_feed, gs_cfg, last_run, is_active)
        try:
            count = await _scrape_global_source_for_keyword(gs, keyword, project_id, since=last_run)
            if count > 0:
                logger.info(f"Global scrape [{latency}]: {count} posts from {gs_name} (keyword={keyword})")
        except Exception:
            logger.exception(f"Global scrape failed: {gs_name} / {keyword}")


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
        logger.info(f"run_batch_scrape started for project {project_id[:8]}")
        async with AsyncSessionLocal() as db:
            project = await db.get(Project, pid)
            if not project or not project.date_from:
                logger.warning(f"run_batch_scrape: project {project_id[:8]} not found or no date_from")
                return
            since = project.date_from
            until = project.date_to
            from models.crud import get_project_global_source_configs
            global_configs = await get_project_global_source_configs(db, pid, date_range_only=True)
            configs = [
                (gs.id, gs.name, gs.source_type, gs.url, gs.feed_url,
                 gs.scraper_config, gs.last_successful_run, gs.is_active, keyword)
                for gs, keyword, latency in global_configs
            ]

        total = 0
        for (gs_id, gs_name, gs_type, gs_url, gs_feed, gs_cfg,
             last_run, is_active, keyword) in configs:
            gs = _make_gs(gs_id, gs_name, gs_type, gs_url, gs_feed, gs_cfg, last_run, is_active)
            try:
                count = await _scrape_global_source_for_keyword(gs, keyword, pid, since=since, until=until)
                total += count
                logger.info(f"  Batch {gs_name} / {keyword}: {count} posts")
            except Exception:
                logger.exception(f"  Batch {gs_name} / {keyword}: failed")

        logger.info(f"Batch scrape done for project {project_id[:8]}: {total} total posts")

    _run_async(_run())


@celery_app.task(name="tasks.scrape_tasks.check_source_health", bind=True, max_retries=1)
def check_source_health(self):
    """HEAD-ping all active global sources every 15 min to detect outages."""
    async def _run():
        import httpx
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(GlobalSource).where(GlobalSource.is_active == True)
            )
            sources = [(s.name, s.url) for s in result.scalars().all()]

        healthy = 0
        unhealthy = 0
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, verify=False) as http:
            for name, url in sources:
                if not url or "{keyword}" in (url or ""):
                    continue
                try:
                    resp = await http.head(url)
                    if resp.status_code < 500:
                        healthy += 1
                    else:
                        unhealthy += 1
                        logger.warning(f"Health: {name} → HTTP {resp.status_code}")
                except Exception as e:
                    unhealthy += 1
                    logger.warning(f"Health: {name} unreachable — {e}")

        logger.info(f"Source health: {healthy} reachable, {unhealthy} unreachable")

    try:
        _run_async(_run())
    except Exception as exc:
        logger.error(f"check_source_health failed: {exc}")
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="tasks.scrape_tasks.scrape_project_now")
def scrape_project_now(project_id: str):
    """On-demand scrape triggered via API — runs all active global sources for the project."""
    async def _run():
        pid = UUID(project_id)
        logger.info(f"scrape_project_now started for project {project_id[:8]}")
        async with AsyncSessionLocal() as db:
            project = await db.get(Project, pid)
            if not project:
                logger.warning(f"scrape_project_now: project {project_id[:8]} not found")
                return
            if getattr(project, 'is_paused', False):
                logger.info(f"scrape_project_now: project {project_id[:8]} is paused, skipping")
                return
            from models.crud import get_project_global_source_configs
            global_configs = await get_project_global_source_configs(db, pid)
            configs = [
                (gs.id, gs.name, gs.source_type, gs.url, gs.feed_url,
                 gs.scraper_config, gs.last_successful_run, gs.is_active, keyword)
                for gs, keyword, latency in global_configs
            ]

        logger.info(f"scrape_project_now: {len(configs)} source-keyword pairs to scrape")
        total = 0
        for (gs_id, gs_name, gs_type, gs_url, gs_feed, gs_cfg,
             last_run, is_active, keyword) in configs:
            gs = _make_gs(gs_id, gs_name, gs_type, gs_url, gs_feed, gs_cfg, last_run, is_active)
            try:
                count = await _scrape_global_source_for_keyword(gs, keyword, pid, since=last_run)
                total += count
                logger.info(f"  {gs_name} / {keyword}: {count} posts")
            except Exception:
                logger.exception(f"  {gs_name} / {keyword}: fetch failed")

        logger.info(f"scrape_project_now done: {total} total posts saved for project {project_id[:8]}")

    _run_async(_run())
