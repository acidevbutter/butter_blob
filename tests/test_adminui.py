from app.adminui.dependencies import get_admin_user_service


async def test_admin_dashboard_login_and_shared_limits(client, db_session, admin_headers):
    unauthenticated = await client.get("/admin", follow_redirects=False)
    assert unauthenticated.status_code == 303
    assert unauthenticated.headers["location"] == "/admin/login"

    service = get_admin_user_service(db_session)
    await service.register("admin@example.com", "safe-password")
    login = await client.post(
        "/admin/login",
        data={"email": "admin@example.com", "password": "safe-password"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert "butter_blob_admin" in login.headers["set-cookie"]

    created = await client.post(
        "/admin/v1/namespaces", json={"slug": "ui-test"}, headers=admin_headers
    )
    assert created.status_code == 201
    dashboard = await client.get("/admin")
    assert dashboard.status_code == 200
    assert "ui-test" in dashboard.text
    detail = await client.get("/admin/namespaces/ui-test")
    assert detail.status_code == 200
    assert 'action="/admin/namespaces/ui-test"' in detail.text

    update = await client.post(
        "/admin/namespaces/ui-test",
        data={"max_storage_bytes": "321", "allowed_extensions": "png, jpg"},
        follow_redirects=False,
    )
    assert update.status_code == 303
    via_json = await client.get("/admin/v1/namespaces/ui-test", headers=admin_headers)
    assert via_json.json()["max_storage_bytes"] == 321
    assert via_json.json()["allowed_extensions"] == [".png", ".jpg"]


async def test_admin_blob_browser_and_soft_delete(client, db_session, internal_headers):
    service = get_admin_user_service(db_session)
    await service.register("operator@example.com", "safe-password")
    await client.post(
        "/admin/login", data={"email": "operator@example.com", "password": "safe-password"}
    )
    uploaded = await client.post(
        "/internal/v1/blobs",
        headers=internal_headers,
        files={"file": ("report.txt", b"dashboard", "text/plain")},
    )
    assert uploaded.status_code == 201
    blob_id = uploaded.json()["id"]

    listed = await client.get("/admin/namespaces/test-app/blobs")
    assert listed.status_code == 200
    assert "report.txt" in listed.text
    detail = await client.get(f"/admin/blobs/{blob_id}")
    assert detail.status_code == 200
    assert "created" in detail.text
    deleted = await client.post(f"/admin/blobs/{blob_id}/delete", follow_redirects=False)
    assert deleted.status_code == 303
    assert "deleted" in (await client.get(f"/admin/blobs/{blob_id}")).text


async def test_admin_dashboard_creates_and_revokes_namespace_api_key(
    client, db_session, admin_headers
):
    service = get_admin_user_service(db_session)
    await service.register("keys@example.com", "safe-password")
    await client.post(
        "/admin/login", data={"email": "keys@example.com", "password": "safe-password"}
    )
    created = await client.post(
        "/admin/v1/namespaces", json={"slug": "dashboard-keys"}, headers=admin_headers
    )
    assert created.status_code == 201

    minted = await client.post(
        "/admin/namespaces/dashboard-keys/keys", data={"label": "backend"}
    )
    assert minted.status_code == 200
    assert minted.headers["cache-control"] == "no-store"
    assert "bbk_" in minted.text

    keys = await client.get("/admin/v1/namespaces/dashboard-keys/keys", headers=admin_headers)
    key_id = keys.json()[0]["id"]
    revoked = await client.post(
        f"/admin/namespaces/dashboard-keys/keys/{key_id}/revoke", follow_redirects=False
    )
    assert revoked.status_code == 303
    assert "Revoked" in (await client.get("/admin/namespaces/dashboard-keys")).text
