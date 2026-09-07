"""Auth-dependency behaviour, exercised through a throwaway router wired to the
same cross-domain guards the real /internal and /admin trees use.
"""

from fastapi import APIRouter

from app.core.dependencies import CallerNamespace, RequireAdminApiKey, RequireServiceApiKey
from app.main import app
from app.settings.config import Settings

_probe = APIRouter(prefix="/_probe", include_in_schema=False)


@_probe.get("/internal", dependencies=[RequireServiceApiKey])
async def _internal(namespace: CallerNamespace) -> dict[str, str]:
    return {"namespace": namespace}


@_probe.get("/admin", dependencies=[RequireAdminApiKey])
async def _admin() -> dict[str, str]:
    return {"ok": "yes"}


app.include_router(_probe)


async def test_internal_without_service_key_is_404(client):
    response = await client.get("/_probe/internal", headers={"X-Blob-Namespace": "acme"})
    assert response.status_code == 404


async def test_internal_with_wrong_service_key_is_404(client):
    response = await client.get(
        "/_probe/internal",
        headers={"X-Service-Api-Key": "nope", "X-Blob-Namespace": "acme"},
    )
    assert response.status_code == 404


async def test_internal_without_namespace_header_is_422(client, internal_headers):
    headers = {"X-Service-Api-Key": internal_headers["X-Service-Api-Key"]}
    response = await client.get("/_probe/internal", headers=headers)
    assert response.status_code == 422


async def test_internal_ok_and_namespace_normalized(client, internal_headers):
    headers = {**internal_headers, "X-Blob-Namespace": "Crate Diggr"}
    response = await client.get("/_probe/internal", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"namespace": "crate-diggr"}


async def test_internal_preserves_underscores_in_namespace(client, internal_headers):
    headers = {**internal_headers, "X-Blob-Namespace": "devbutter_backend"}
    response = await client.get("/_probe/internal", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"namespace": "devbutter_backend"}


async def test_admin_without_key_is_404(client):
    response = await client.get("/_probe/admin")
    assert response.status_code == 404


async def test_admin_with_key_ok(client, admin_headers):
    response = await client.get("/_probe/admin", headers=admin_headers)
    assert response.status_code == 200


def test_thumbnail_width_setting_accepts_single_documented_value():
    assert Settings(thumbnail_widths=256).thumbnail_widths == [256]
