#!/bin/sh
# SERVICE_TYPE controls which process this container runs.
# Set SERVICE_TYPE=worker or SERVICE_TYPE=beat in Railway env vars.
# Defaults to "api" (uvicorn).
case "${SERVICE_TYPE:-api}" in
  worker)
    exec celery -A tasks.celery_app worker --loglevel=info --concurrency=2 -Q celery,pipeline,scrape
    ;;
  beat)
    exec celery -A tasks.celery_app beat --loglevel=info --scheduler celery.beat:PersistentScheduler
    ;;
  *)
    exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
esac
