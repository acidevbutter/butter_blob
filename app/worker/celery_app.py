"""Celery app + broker config, shared by app.core.jobs (producer, imported by
the API process -- blobs/service.py) and the worker CLI (consumer).

Start the worker with:
    celery -A app.worker.celery_app:celery_app worker --loglevel=info -Q blob-jobs
"""

from __future__ import annotations

from celery import Celery

from app.settings.config import settings

TASK_NAME = "butter_blob.process_job"

celery_app = Celery(
    "butter_blob",
    broker=settings.redis_url,
    backend=settings.redis_url,
    # Deferred import: app.worker.tasks pulls in Pillow/clamd socket code that
    # the API process (a producer via app.core.jobs) has no reason to load.
    # Celery only imports `include` modules inside the worker process itself.
    include=["app.worker.tasks"],
)
celery_app.conf.update(
    task_default_queue=settings.redis_queue_name,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=300,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
)
