"""Small async facade for the SQS queue used by blob post-processing."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import boto3
from botocore.client import Config

from app.settings.config import settings


def build_sqs_client() -> Any:
    return boto3.client(
        "sqs",
        region_name=settings.aws_region,
        endpoint_url=settings.blob_jobs_endpoint_url or None,
        config=Config(signature_version="v4"),
    )


async def enqueue(job: dict[str, Any]) -> None:
    """Send one serializable blob job without blocking the API event loop."""
    if not settings.blob_jobs_queue_url:
        return
    client = build_sqs_client()
    await asyncio.to_thread(
        client.send_message,
        QueueUrl=settings.blob_jobs_queue_url,
        MessageBody=json.dumps(job),
    )
