from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adminui.models import AdminUser
from app.core.exceptions import ConflictError


class AdminUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: UUID) -> AdminUser | None:
        return await self.session.get(AdminUser, user_id)

    async def get_by_email(self, email: str) -> AdminUser | None:
        result = await self.session.execute(select(AdminUser).where(AdminUser.email == email))
        return result.scalar_one_or_none()

    async def create(self, email: str, password_hash: str) -> AdminUser:
        user = AdminUser(email=email, password_hash=password_hash)
        self.session.add(user)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(f"An admin user with email {email!r} already exists") from exc
        await self.session.refresh(user)
        return user
