"""Inicio de sesión, sesiones abiertas y alta de usuarios."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError, integrity_conflict
from app.core.permissions import UserRole
from app.core.security import hash_password, hash_token, new_session_token, verify_password
from app.models.user import User, UserSession
from app.schemas.auth import UserCreate, UserUpdate

SESSION_TTL = timedelta(hours=12)


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def login(
        self,
        email: str,
        password: str,
        *,
        user_agent: str | None = None,
    ) -> tuple[User, str, datetime]:
        """Devuelve el usuario, el token en claro y hasta cuándo vale.

        El mismo error para usuario inexistente, contraseña equivocada y usuario dado de
        baja: decir cuál de las tres es sirve para averiguar quién tiene cuenta.
        """

        invalid = DomainError("Usuario o contraseña incorrectos", 401)
        token = new_session_token()
        now = datetime.now(UTC)
        expires_at = now + SESSION_TTL
        async with self.session.begin():
            user = await self.session.scalar(
                select(User).where(User.email == email.strip().lower())
            )
            if not user or not user.is_active:
                raise invalid
            if not verify_password(password, user.password_hash):
                raise invalid
            self.session.add(
                UserSession(
                    user_id=user.id,
                    token_hash=hash_token(token),
                    expires_at=expires_at,
                    user_agent=user_agent,
                )
            )
            user.last_login_at = now
        return user, token, expires_at

    async def resolve(self, token: str) -> User:
        """Usuario de una sesión vigente. Sesión vencida o revocada es sesión inexistente."""

        session_row = await self.session.scalar(
            select(UserSession).where(UserSession.token_hash == hash_token(token))
        )
        expired = DomainError("Sesión inválida o vencida", 401)
        if not session_row or session_row.revoked_at is not None:
            raise expired
        if session_row.expires_at <= datetime.now(UTC):
            raise expired
        user = await self.session.get(User, session_row.user_id)
        if not user or not user.is_active:
            raise expired
        return user

    async def logout(self, token: str) -> None:
        """Cerrar sesión es revocar el token; hacerlo dos veces no es un error."""

        async with self.session.begin():
            session_row = await self.session.scalar(
                select(UserSession).where(UserSession.token_hash == hash_token(token))
            )
            if session_row and session_row.revoked_at is None:
                session_row.revoked_at = datetime.now(UTC)

    async def list_users(self) -> list[User]:
        return list((await self.session.scalars(select(User).order_by(User.full_name))).all())

    async def get(self, user_id: uuid.UUID) -> User:
        user = await self.session.get(User, user_id)
        if not user:
            raise DomainError("Usuario inexistente", 404)
        return user

    async def create_user(self, payload: UserCreate) -> User:
        async with (
            integrity_conflict(self.session, "Ya existe un usuario con ese correo"),
            self.session.begin(),
        ):
            user = User(
                email=payload.email.strip().lower(),
                full_name=payload.full_name.strip(),
                role=payload.role,
                password_hash=hash_password(payload.password),
                is_active=payload.is_active,
            )
            self.session.add(user)
            await self.session.flush()
            return user

    async def update_user(self, user_id: uuid.UUID, payload: UserUpdate) -> User:
        """Cambiar el rol o dar de baja cierra las sesiones abiertas: los permisos que
        tenía el usuario no siguen valiendo con la pantalla ya abierta."""

        async with (
            integrity_conflict(self.session, "Ya existe un usuario con ese correo"),
            self.session.begin(),
        ):
            user = await self.get(user_id)
            revoke = user.role != payload.role or (user.is_active and not payload.is_active)
            user.email = payload.email.strip().lower()
            user.full_name = payload.full_name.strip()
            user.role = payload.role
            user.is_active = payload.is_active
            if payload.password:
                user.password_hash = hash_password(payload.password)
                revoke = True
            if revoke:
                await self._revoke_sessions(user.id)
            await self.session.flush()
            return user

    async def _revoke_sessions(self, user_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        rows = await self.session.scalars(
            select(UserSession).where(
                UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
            )
        )
        for row in rows:
            row.revoked_at = now


async def ensure_user(
    session: AsyncSession,
    *,
    email: str,
    full_name: str,
    role: UserRole,
    password: str,
) -> tuple[User, bool]:
    """Crea el usuario si no existe. No pisa la contraseña de uno ya creado."""

    email = email.strip().lower()
    user = await session.scalar(select(User).where(User.email == email))
    if user:
        return user, False
    user = User(
        email=email,
        full_name=full_name,
        role=role,
        password_hash=hash_password(password),
    )
    session.add(user)
    await session.flush()
    return user, True
