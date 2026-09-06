from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from app.adminui.models import AdminUser
from app.adminui.repository import AdminUserRepository
from app.adminui.service import AdminUserService
from app.core.dependencies import DbSession
from app.core.exceptions import SessionRequiredError


def get_admin_user_service(db: DbSession) -> AdminUserService:
    return AdminUserService(AdminUserRepository(db))


AdminUserServiceDep = Annotated[AdminUserService, Depends(get_admin_user_service)]


async def get_current_admin(request: Request, service: AdminUserServiceDep) -> AdminUser:
    user_id = request.session.get("admin_user_id")
    if user_id is None:
        raise SessionRequiredError()
    try:
        user = await service.get(UUID(user_id))
    except ValueError as exc:
        raise SessionRequiredError() from exc
    if user is None or not user.is_active:
        raise SessionRequiredError()
    return user


CurrentAdmin = Annotated[AdminUser, Depends(get_current_admin)]
