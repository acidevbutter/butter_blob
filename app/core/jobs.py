"""Small async facade for the Celery/Redis queue used by blob post-processing."""

from __future__ import annotations

import asyncio
from typing import Any

from app.settings.config import settings
from app.worker.celery_app import TASK_NAME, celery_app


async def enqueue(job: dict[str, Any]) -> None:
    """Send one serializable blob job without blocking the API event loop."""
    if not settings.redis_url:
        return
    await asyncio.to_thread(
        celery_app.send_task,
        TASK_NAME,
        kwargs=job,
        queue=settings.redis_queue_name,
    )
