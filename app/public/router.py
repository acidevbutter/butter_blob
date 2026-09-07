from typing import Literal

from fastapi import APIRouter, Response
from fastapi.responses import RedirectResponse

from app.public.dependencies import PublicServiceDep
from app.public.schemas import PublicMeta

router = APIRouter(prefix="/v1/public", tags=["public"])


@router.get("/{namespace}/{public_slug}/meta", response_model=PublicMeta)
async def public_meta(
    namespace: str, public_slug: str, service: PublicServiceDep, response: Response
) -> PublicMeta:
    response.headers["Cache-Control"] = await service.cache_control(namespace, public_slug)
    return await service.meta(namespace, public_slug)


@router.get("/{namespace}/{public_slug}")
async def public_blob(
    namespace: str,
    public_slug: str,
    service: PublicServiceDep,
    disposition: Literal["inline", "attachment"] = "inline",
) -> RedirectResponse:
    url = await service.redirect_url(namespace, public_slug, disposition=disposition)
    return RedirectResponse(
        url=url,
        status_code=302,
        headers={"Cache-Control": await service.cache_control(namespace, public_slug)},
    )
