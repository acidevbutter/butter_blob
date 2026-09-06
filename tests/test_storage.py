import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from app.core import storage as storage_module
from app.core.exceptions import NotFoundError, StorageError
from app.core.storage import BlobStorage
from tests.fakes import InMemoryBlobStorage

BUCKET = "unit-test-bucket"


@pytest.fixture
def aws_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


async def test_inmemory_round_trip():
    fake = InMemoryBlobStorage()
    await fake.put_object("blobs/acme/1/logo.png", b"binary-bytes", "image/png")

    head = await fake.head_object("blobs/acme/1/logo.png")
    assert head.size == len(b"binary-bytes")
    assert head.content_type == "image/png"

    assert await fake.get_object("blobs/acme/1/logo.png") == b"binary-bytes"

    await fake.delete_object("blobs/acme/1/logo.png")
    with pytest.raises(NotFoundError):
        await fake.get_object("blobs/acme/1/logo.png")


async def test_inmemory_presigned_shapes():
    fake = InMemoryBlobStorage()
    put_url = await fake.generate_presigned_put("k", "text/plain", 900)
    assert put_url.startswith("https://fake-s3.local/") and "method=PUT" in put_url

    get_url = await fake.generate_presigned_get("k", 300, disposition="attachment")
    assert "method=GET" in get_url and "disposition=attachment" in get_url


async def test_real_storage_round_trip_with_moto(aws_credentials):
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        store = BlobStorage(bucket=BUCKET)

        await store.put_object("blobs/acme/1/report.pdf", b"%PDF-1.7 ...", "application/pdf")
        head = await store.head_object("blobs/acme/1/report.pdf")
        assert head.size == len(b"%PDF-1.7 ...")
        assert head.content_type == "application/pdf"
        assert await store.get_object("blobs/acme/1/report.pdf") == b"%PDF-1.7 ..."

        assert await store.bucket_exists() is True

        await store.delete_object("blobs/acme/1/report.pdf")
        with pytest.raises(NotFoundError):
            await store.head_object("blobs/acme/1/report.pdf")


async def test_bucket_exists_false_when_missing(aws_credentials):
    with mock_aws():
        store = BlobStorage(bucket="nonexistent-bucket")
        assert await store.bucket_exists() is False


async def test_client_error_becomes_storage_error_and_emits_metric(aws_credentials, monkeypatch):
    with mock_aws():
        store = BlobStorage(bucket=BUCKET)

        def _raise(**kwargs):
            raise ClientError({"Error": {"Code": "500", "Message": "boom"}}, "PutObject")

        monkeypatch.setattr(store._client, "put_object", _raise)

        calls: list[dict[str, object]] = []

        async def _capture(name, value=1, unit="Count", *, namespace=None, **dims):
            calls.append({"name": name, "dims": dims})

        monkeypatch.setattr(storage_module, "emit_blob_metric", _capture)

        with pytest.raises(StorageError):
            await store.put_object("k", b"x", "text/plain")

        assert calls == [{"name": "StorageErrorCount", "dims": {"Operation": "put_object"}}]
