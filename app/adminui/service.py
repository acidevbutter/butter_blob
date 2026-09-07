from uuid import UUID

import bcrypt

from app.adminui.models import AdminUser
from app.adminui.repository import AdminUserRepository
from app.core.decorators import log_errors
from app.core.exceptions import UnauthorizedError


@log_errors
class AdminUserService:
    def __init__(self, repository: AdminUserRepository) -> None:
        self.repository = repository

    async def register(self, email: str, password: str) -> AdminUser:
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        return await self.repository.create(email.strip().lower(), password_hash)

    async def verify(self, email: str, password: str) -> AdminUser:
        user = await self.repository.get_by_email(email.strip().lower())
        if user is None or not user.is_active or not bcrypt.checkpw(
            password.encode(), user.password_hash.encode()
        ):
            raise UnauthorizedError("Invalid email or password")
        return user

    async def get(self, user_id: UUID) -> AdminUser | None:
        return await self.repository.get(user_id)
