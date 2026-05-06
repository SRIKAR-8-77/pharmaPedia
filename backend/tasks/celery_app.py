from celery import Celery
from celery.schedules import crontab
from config import settings

celery_app = Celery(
    "pharmasignal",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "tasks.scrape_tasks",
        "tasks.pipeline_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "tasks.scrape_tasks.*": {"queue": "scrape"},
        "tasks.pipeline_tasks.*": {"queue": "pipeline"},
    },
)

# ─── Periodic schedules ───────────────────────────────────────────────────────
celery_app.conf.beat_schedule = {
    # Run realtime sources every 5 minutes (prevents worker saturation)
    "scrape-realtime-sources": {
        "task": "tasks.scrape_tasks.run_realtime_sources",
        "schedule": 300.0,
    },
    # Run daily sources once per day at 06:00 UTC
    "scrape-daily-sources": {
        "task": "tasks.scrape_tasks.run_daily_sources",
        "schedule": crontab(hour=6, minute=0),
    },
    # Run weekly sources every Monday at 07:00 UTC
    "scrape-weekly-sources": {
        "task": "tasks.scrape_tasks.run_weekly_sources",
        "schedule": crontab(hour=7, minute=0, day_of_week="monday"),
    },
    # Run pipeline on unprocessed posts every 5 minutes
    "run-pipeline-batch": {
        "task": "tasks.pipeline_tasks.run_pipeline_all_projects",
        "schedule": 300.0,
    },
    # Source health check every 15 minutes
    "health-check-sources": {
        "task": "tasks.scrape_tasks.check_source_health",
        "schedule": 900.0,
    },
    # Weekly report generation — every Monday at 08:00 UTC
    "generate-weekly-reports": {
        "task": "tasks.pipeline_tasks.generate_weekly_reports",
        "schedule": crontab(hour=8, minute=0, day_of_week="monday"),
    },
}
