async def test_admin_namespace_create_conflicts_on_duplicate(client, admin_headers):
    payload = {"slug": "crate_diggr", "name": "Crate Diggr"}

    created = await client.post("/admin/v1/namespaces", json=payload, headers=admin_headers)
    duplicate = await client.post("/admin/v1/namespaces", json=payload, headers=admin_headers)

    assert created.status_code == 201
    assert duplicate.status_code == 409


async def test_admin_sets_and_reads_namespace_limits(client, admin_headers):
    created = await client.post(
        "/admin/v1/namespaces", json={"slug": "crate_diggr"}, headers=admin_headers
    )
    assert created.status_code == 201

    limits = {
        "max_storage_bytes": 1000,
        "max_file_bytes": 500,
        "allowed_content_types": [" Image/PNG ", "image/png", "application/pdf"],
        "allowed_extensions": ["PNG", ".pdf", ".PNG"],
        "image_compression_quality": 80,
        "image_max_dimension": 1200,
    }
    updated = await client.put(
        "/admin/v1/namespaces/crate_diggr/limits", json=limits, headers=admin_headers
    )
    read = await client.get("/admin/v1/namespaces/crate_diggr", headers=admin_headers)

    assert updated.status_code == 200
    assert read.status_code == 200
    assert read.json()["max_storage_bytes"] == 1000
    assert read.json()["allowed_content_types"] == ["image/png", "application/pdf"]
    assert read.json()["allowed_extensions"] == [".png", ".pdf"]
    assert read.json()["image_compression_quality"] == 80


async def test_admin_rejects_invalid_compression_quality(client, admin_headers):
    for quality in (0, 101):
        response = await client.put(
            "/admin/v1/namespaces/missing/limits",
            json={"image_compression_quality": quality},
            headers=admin_headers,
        )
        assert response.status_code == 422


async def test_admin_routes_are_hidden_without_key(client):
    response = await client.get("/admin/v1/namespaces")
    assert response.status_code == 404
