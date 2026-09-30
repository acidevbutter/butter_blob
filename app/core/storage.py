"""S3 / MinIO access, isolated behind BlobStorage so the service layer never
imports boto3 and never sees a botocore exception -- every failure is translated
to app.core.exceptions.StorageError (or NotFoundError for a missing object).

boto3 has no native asyncio support, so every call is pushed to a worker thread
with asyncio.to_thread (same approach app.worker.tasks uses for the ClamAV
socket call).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any, cast
from urllib.parse import urlsplit, urlunsplit

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends
from urllib3.exceptions import HTTPError

from app.core.decorators import log_errors
from app.core.exceptions import NotFoundError, StorageError
from app.core.observability import emit_blob_metric
from app.settings.config import settings

logger = logging.getLogger(__name__)

_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}


def _make_public(url: str) -> str:
    """Rewrite a presigned URL's host from settings.s3_endpoint_url (the internal
    Docker Compose hostname boto3 signs against) to settings.s3_public_endpoint_url
    (the browser-reachable equivalent). No-op unless both are configured and the
    URL's host actually matches -- i.e. a no-op in every environment but local dev.
    """
    if not settings.s3_public_endpoint_url or not settings.s3_endpoint_url:
        return url
    internal = urlsplit(settings.s3_endpoint_url)
    public = urlsplit(settings.s3_public_endpoint_url)
    parts = urlsplit(url)
    if parts.netloc != internal.netloc:
        return url
    return urlunsplit((public.scheme, public.netloc, parts.path, parts.query, parts.fragment))


class HeadObject:
    """Plain result object for head_object -- avoids leaking the raw boto3 dict."""

    __slots__ = ("size", "etag", "content_type")

    def __init__(self, size: int, etag: str | None, content_type: str | None):
        self.size = size
        self.etag = etag
        self.content_type = content_type


@log_errors
class BlobStorage:
    def __init__(self, *, bucket: str | None = None) -> None:
        self.bucket = bucket or settings.s3_bucket
        addressing = "path" if settings.s3_force_path_style else "auto"
        self._client: Any = boto3.client(
            "s3",
            region_name=settings.aws_region,
            endpoint_url=settings.s3_endpoint_url or None,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": addressing},
            ),
        )

    async def _run(self, operation: str, func: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if operation == "head_object" and code in _NOT_FOUND_CODES:
                raise NotFoundError(f"Object {kwargs.get('Key', args)} not found") from exc
            await emit_blob_metric("StorageErrorCount", Operation=operation)
            raise StorageError(f"S3 {operation} failed: {code or exc}") from exc
        except (BotoCoreError, HTTPError) as exc:
            await emit_blob_metric("StorageErrorCount", Operation=operation)
            raise StorageError(f"S3 {operation} failed: {exc}") from exc

    async def put_object(self, key: str, data: bytes, content_type: str) -> None:
        await self._run(
            "put_object",
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def get_object(self, key: str) -> bytes:
        def _download() -> bytes:
            result = self._client.get_object(Bucket=self.bucket, Key=key)
            return cast(bytes, result["Body"].read())

        return cast(bytes, await self._run("get_object", _download))

    async def head_object(self, key: str) -> HeadObject:
        result = await self._run(
            "head_object", self._client.head_object, Bucket=self.bucket, Key=key
        )
        size = int(result.get("ContentLength", 0))
        etag_raw = result.get("ETag")
        etag = str(etag_raw).strip('"') if etag_raw is not None else None
        content_type_raw = result.get("ContentType")
        content_type = str(content_type_raw) if content_type_raw is not None else None
        return HeadObject(size=size, etag=etag, content_type=content_type)

    async def delete_object(self, key: str) -> None:
        # S3 delete of a missing key is a no-op, so this is safe to call twice.
        await self._run(
            "delete_object", self._client.delete_object, Bucket=self.bucket, Key=key
        )

    async def generate_presigned_put(
        self, key: str, content_type: str, expires: int
    ) -> str:
        url: str = await self._run(
            "generate_presigned_url",
            self._client.generate_presigned_url,
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires,
        )
        return _make_public(url)

    async def generate_presigned_get(
        self,
        key: str,
        expires: int,
        *,
        disposition: str | None = None,
        filename: str | None = None,
    ) -> str:
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if disposition:
            value = disposition
            if filename:
                value = f'{disposition}; filename="{filename}"'
            params["ResponseContentDisposition"] = value
        url: str = await self._run(
            "generate_presigned_url",
            self._client.generate_presigned_url,
            "get_object",
            Params=params,
            ExpiresIn=expires,
        )
        return _make_public(url)

    async def bucket_exists(self) -> bool:
        """Used by /health/ready. Returns False (never raises) so a storage
        outage surfaces as a 503, not a 500.
        """
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self.bucket)
            return True
        except (ClientError, BotoCoreError):
            logger.warning("S3 bucket %s not reachable", self.bucket)
            return False


_blob_storage: BlobStorage | None = None


def get_blob_storage() -> BlobStorage:
    global _blob_storage
    if _blob_storage is None:
        _blob_storage = BlobStorage()
    return _blob_storage


BlobStorageDep = Annotated[BlobStorage, Depends(get_blob_storage)]
