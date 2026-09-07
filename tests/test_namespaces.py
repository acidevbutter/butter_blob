async def test_first_internal_call_creates_namespace(client, internal_headers):
    response = await client.get("/internal/v1/namespaces/test-app", headers=internal_headers)

    assert response.status_code == 200
    assert response.json()["slug"] == "test-app"
    assert response.json()["blob_count"] == 0


async def test_namespace_get_and_patch_hide_other_namespaces(client, internal_headers):
    response = await client.get("/internal/v1/namespaces/other", headers=internal_headers)
    assert response.status_code == 404

    response = await client.patch(
        "/internal/v1/namespaces/other", json={"name": "Nope"}, headers=internal_headers
    )
    assert response.status_code == 404


async def test_namespace_self_update_only_changes_self_service_fields(client, internal_headers):
    response = await client.patch(
        "/internal/v1/namespaces/test-app",
        json={"name": "Test app", "description": "A test namespace"},
        headers=internal_headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Test app"
    assert response.json()["description"] == "A test namespace"
