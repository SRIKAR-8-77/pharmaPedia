"""
Pipeline Celery tasks.
The actual pipeline steps live in /pipeline/ — these tasks just trigger them.
Phase 1: stubs that will be filled in Phase 2.
"""
import logging
import asyncio
from uuid import UUID

from tasks.celery_app import celery_app
from models.database import AsyncSessionLocal, Project
from sqlalchemy import select

logger = logging.getLogger(__name__)


def _run_async(coro):
    from models.database import engine
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)


@celery_app.task(name="tasks.pipeline_tasks.run_pipeline_for_project")
def run_pipeline_for_project(project_id: str):
    """Process all unprocessed raw_posts for a project through the NLP pipeline."""
    import sys, os
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)

    from pipeline.runner import run_pipeline

    async def _run():
        stats = await run_pipeline(UUID(project_id))
        logger.info(
            f"Pipeline done [{project_id[:8]}]: "
            f"{stats.processed}/{stats.total} posts, "
            f"{stats.high_signals} HIGH signals"
        )

    _run_async(_run())


@celery_app.task(name="tasks.pipeline_tasks.run_pipeline_all_projects")
def run_pipeline_all_projects():
    """Batch pipeline run across all active projects (called by Celery beat every 5 min)."""
    async def _run():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Project.id).where(
                    Project.is_active == True,
                    Project.is_paused == False,
                )
            )
            project_ids = [str(row[0]) for row in result.all()]

        for pid in project_ids:
            run_pipeline_for_project.delay(pid)

    _run_async(_run())


@celery_app.task(name="tasks.pipeline_tasks.generate_weekly_reports")
def generate_weekly_reports():
    """Generate weekly digest reports for all active projects (Phase 4/5)."""
    async def _run():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Project.id).where(
                    Project.is_active == True,
                    Project.is_paused == False,
                )
            )
            project_ids = [str(row[0]) for row in result.all()]

        for pid in project_ids:
            try:
                from agents.report_generator import generate_report
                await generate_report(UUID(pid))
            except ImportError:
                logger.info("Report agent not yet implemented (Phase 5)")

    _run_async(_run())
