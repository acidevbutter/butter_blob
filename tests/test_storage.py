import boto3
import pytest
from botocore.exceptions import ClientError, ReadTimeoutError
from moto import mock_aws
from urllib3.exceptions import HTTPError

from app.core.exceptions import NotFoundError, StorageError
from app.core.storage import BlobStorage, _make_public
from app.settings.config import settings
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


def test_make_public_rewrites_internal_host_to_public_one(monkeypatch):
    monkeypatch.setattr(settings, "s3_endpoint_url", "http://minio:9000")
    monkeypatch.setattr(settings, "s3_public_endpoint_url", "http://localhost:9010")

    url = "http://minio:9000/devbutter-blob-local/blobs/acme/key.png?X-Amz-Signature=abc"

    assert _make_public(url) == "http://localhost:9010/devbutter-blob-local/blobs/acme/key.png?X-Amz-Signature=abc"


def test_make_public_is_a_noop_without_a_public_endpoint_configured(monkeypatch):
    monkeypatch.setattr(settings, "s3_endpoint_url", "http://minio:9000")
    monkeypatch.setattr(settings, "s3_public_endpoint_url", None)

    url = "http://minio:9000/devbutter-blob-local/blobs/acme/key.png"
    assert _make_public(url) == url


def test_make_public_is_a_noop_for_a_real_s3_host(monkeypatch):
    # Guards against ever rewriting a real AWS S3 URL: s3_endpoint_url is
    # empty outside development (config.py rejects setting it otherwise), so
    # the host-match check in _make_public never fires.
    monkeypatch.setattr(settings, "s3_endpoint_url", None)
    monkeypatch.setattr(settings, "s3_public_endpoint_url", "http://localhost:9010")

    url = "https://unit-test-bucket.s3.amazonaws.com/blobs/acme/key.png"
    assert _make_public(url) == url


async def test_generate_presigned_get_rewrites_to_the_public_endpoint(aws_credentials, monkeypatch):
    # No mock_aws()/real client here: generate_presigned_url is stubbed directly
    # below, so BlobStorage never makes a network call worth sandboxing --
    # moto's interception is unreliable once endpoint_url is overridden anyway.
    monkeypatch.setattr(settings, "s3_endpoint_url", "http://minio:9000")
    monkeypatch.setattr(settings, "s3_public_endpoint_url", "http://localhost:9010")
    store = BlobStorage(bucket=BUCKET)
    monkeypatch.setattr(
        store._client, "generate_presigned_url", lambda *a, **k: "http://minio:9000/signed?x=1"
    )

    url = await store.generate_presigned_get("k", 300)

    assert url == "http://localhost:9010/signed?x=1"


async def test_bucket_exists_false_when_missing(aws_credentials):
    with mock_aws():
        store = BlobStorage(bucket="nonexistent-bucket")
        assert await store.bucket_exists() is False


async def test_client_error_becomes_storage_error(aws_credentials, monkeypatch):
    with mock_aws():
        store = BlobStorage(bucket=BUCKET)

        def _raise(**kwargs):
            raise ClientError({"Error": {"Code": "500", "Message": "boom"}}, "PutObject")

        monkeypatch.setattr(store._client, "put_object", _raise)

        with pytest.raises(StorageError):
            await store.put_object("k", b"x", "text/plain")



@pytest.mark.parametrize(
    "read_error",
    [
        ReadTimeoutError(endpoint_url="http://s3.local", error="boom"),
        HTTPError("connection broken"),
    ],
)
async def test_download_read_error_becomes_storage_error(
    aws_credentials, monkeypatch, read_error
):
    with mock_aws():
        store = BlobStorage(bucket=BUCKET)

        class BrokenBody:
            def read(self) -> bytes:
                raise read_error

        monkeypatch.setattr(store._client, "get_object", lambda **kwargs: {"Body": BrokenBody()})

        with pytest.raises(StorageError):
            await store.get_object("k")

