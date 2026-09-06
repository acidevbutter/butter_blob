"""In-memory stand-in for app.core.storage.BlobStorage so tests never need a real
S3 / MinIO. Same public interface; presigned URLs are deterministic fake strings.
"""

from __future__ import annotations

from urllib.parse import quote

from app.core.exceptions import NotFoundError
from app.core.storage import HeadObject


class InMemoryBlobStorage:
    def __init__(self, *, bucket: str = "test-bucket") -> None:
        self.bucket = bucket
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.bucket_present = True

    async def put_object(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    async def get_object(self, key: str) -> bytes:
        if key not in self.objects:
            raise NotFoundError(f"Object {key} not found")
        return self.objects[key][0]

    async def head_object(self, key: str) -> HeadObject:
        if key not in self.objects:
            raise NotFoundError(f"Object {key} not found")
        data, content_type = self.objects[key]
        return HeadObject(size=len(data), etag="fake-etag", content_type=content_type)

    async def delete_object(self, key: str) -> None:
        self.objects.pop(key, None)

    async def generate_presigned_put(self, key: str, content_type: str, expires: int) -> str:
        return f"https://fake-s3.local/{self.bucket}/{quote(key)}?method=PUT&expires={expires}"

    async def generate_presigned_get(
        self,
        key: str,
        expires: int,
        *,
        disposition: str | None = None,
        filename: str | None = None,
    ) -> str:
        url = f"https://fake-s3.local/{self.bucket}/{quote(key)}?method=GET&expires={expires}"
        if disposition:
            url += f"&disposition={disposition}"
        return url

    async def bucket_exists(self) -> bool:
        return self.bucket_present
