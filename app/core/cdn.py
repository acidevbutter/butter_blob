"""CloudFront invalidation for public permanent blobs."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.settings.config import settings

logger = logging.getLogger(__name__)


async def invalidate(paths: list[str]) -> None:
    """Invalidate object paths when the public CDN is configured.

    A missing CDN configuration deliberately keeps local MinIO development free
    of CloudFront calls. Invalidation errors are logged: storage changes have
    already succeeded and a stale edge object must not make the API fail.
    """
    if not settings.public_cdn_base_url or not settings.cloudfront_distribution_id:
        return

    normalized_paths = [path if path.startswith("/") else f"/{path}" for path in paths]
    if not normalized_paths:
        return

    def _create_invalidation() -> Any:
        client = boto3.client("cloudfront")
        return client.create_invalidation(
            DistributionId=settings.cloudfront_distribution_id,
            InvalidationBatch={
                "Paths": {"Quantity": len(normalized_paths), "Items": normalized_paths},
                "CallerReference": str(uuid4()),
            },
        )

    try:
        await asyncio.to_thread(_create_invalidation)
    except (BotoCoreError, ClientError):
        logger.warning("CloudFront invalidation failed", exc_info=True)
