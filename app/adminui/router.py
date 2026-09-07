from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.adminui.dependencies import AdminUserServiceDep, CurrentAdmin
from app.adminui.templating import render
from app.blobs.dependencies import BlobServiceDep
from app.blobs.models import BlobStatus, Visibility
from app.blobs.repository import BlobRepository
from app.core.dependencies import DbSession
from app.core.exceptions import UnauthorizedError
from app.namespaces.dependencies import NamespaceServiceDep
from app.namespaces.schemas import NamespaceLimitsUpdate

router = APIRouter(prefix="/admin", tags=["admin-ui"])


def _optional_int(value: str) -> int | None:
    return int(value) if value.strip() else None


def _optional_list(value: str) -> list[str] | None:
    return [item.strip() for item in value.split(",") if item.strip()] or None


@router.get("/login", include_in_schema=False)
async def login_form(request: Request) -> HTMLResponse:
    return render(request, "login.html", error=None)


@router.post("/login", include_in_schema=False)
async def login(
    request: Request,
    service: AdminUserServiceDep,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Response:
    try:
        user = await service.verify(email, password)
    except UnauthorizedError as exc:
        return render(request, "login.html", error=exc.detail)
    request.session["admin_user_id"] = str(user.id)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/logout", include_in_schema=False)
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=303)


@router.get("", include_in_schema=False)
async def dashboard(
    request: Request, admin_user: CurrentAdmin, namespaces: NamespaceServiceDep
) -> HTMLResponse:
    return render(
        request,
        "dashboard.html",
        admin_user=admin_user,
        namespaces=await namespaces.list_with_usage(),
    )


@router.get("/namespaces/{slug}", include_in_schema=False)
async def namespace_detail(
    slug: str, request: Request, admin_user: CurrentAdmin, namespaces: NamespaceServiceDep
) -> HTMLResponse:
    return render(
        request,
        "namespace_detail.html",
        admin_user=admin_user,
        namespace=await namespaces.get_usage(slug),
    )


@router.post("/namespaces/{slug}", include_in_schema=False)
async def update_namespace_limits(
    slug: str,
    admin_user: CurrentAdmin,
    namespaces: NamespaceServiceDep,
    max_storage_bytes: Annotated[str, Form()] = "",
    max_file_bytes: Annotated[str, Form()] = "",
    allowed_content_types: Annotated[str, Form()] = "",
    allowed_extensions: Annotated[str, Form()] = "",
    image_compression_quality: Annotated[str, Form()] = "",
    image_max_dimension: Annotated[str, Form()] = "",
) -> RedirectResponse:
    del admin_user
    await namespaces.set_limits(
        slug,
        NamespaceLimitsUpdate(
            max_storage_bytes=_optional_int(max_storage_bytes),
            max_file_bytes=_optional_int(max_file_bytes),
            allowed_content_types=_optional_list(allowed_content_types),
            allowed_extensions=_optional_list(allowed_extensions),
            image_compression_quality=_optional_int(image_compression_quality),
            image_max_dimension=_optional_int(image_max_dimension),
        ),
    )
    return RedirectResponse(url=f"/admin/namespaces/{slug}", status_code=303)


@router.get("/namespaces/{slug}/blobs", include_in_schema=False)
async def list_namespace_blobs(
    slug: str,
    request: Request,
    admin_user: CurrentAdmin,
    db: DbSession,
    visibility: Visibility | None = None,
    status: BlobStatus | None = None,
) -> HTMLResponse:
    blobs = await BlobRepository(db).list(
        slug, visibility=visibility, status=status, limit=200
    )
    return render(
        request,
        "blobs.html",
        admin_user=admin_user,
        namespace=slug,
        blobs=blobs,
        visibility=visibility,
        status=status,
    )


@router.get("/blobs/{blob_id}", include_in_schema=False)
async def blob_detail(
    blob_id: UUID, request: Request, admin_user: CurrentAdmin, db: DbSession
) -> HTMLResponse:
    repo = BlobRepository(db)
    blob = await repo.get(blob_id)
    if blob is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError()
    return render(
        request,
        "blob_detail.html",
        admin_user=admin_user,
        blob=blob,
        events=await repo.list_events(blob.id),
    )


@router.post("/blobs/{blob_id}/delete", include_in_schema=False)
async def delete_blob(
    blob_id: UUID, admin_user: CurrentAdmin, service: BlobServiceDep, db: DbSession
) -> RedirectResponse:
    del admin_user
    blob = await BlobRepository(db).get(blob_id)
    if blob is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError()
    await service.delete(blob.namespace, blob.id, hard=False)
    return RedirectResponse(url=f"/admin/namespaces/{blob.namespace}/blobs", status_code=303)
