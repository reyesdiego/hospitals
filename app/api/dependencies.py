"""Sesión de base, usuario autenticado y permisos."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import permission_for
from app.core.config import settings
from app.core.exceptions import DomainError
from app.core.permissions import Permission, UserRole, permissions_of
from app.core.users import RequestUser
from app.db.session import get_db_session
from app.services.auth import AuthService

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@dataclass(frozen=True)
class SessionUser:
    """El usuario de la sesión, ya leído.

    Son datos sueltos y no la entidad ``User``: así el resto del request no depende de que
    la fila siga adjunta a la sesión.
    """

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime

    @property
    def permissions(self) -> list[Permission]:
        return sorted(permissions_of(self.role), key=lambda item: item.value)


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise DomainError("Inicie sesión para continuar", 401)
    return token.strip()


async def authenticated_user(
    session: DbSession,
    token: Annotated[str, Depends(bearer_token)],
) -> SessionUser:
    user = await AuthService(session).resolve(token)
    resolved = SessionUser(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )
    # Leer abre una transacción implícita, y los servicios abren la suya con
    # ``session.begin()``: sin este cierre, toda escritura autenticada fallaría.
    await session.rollback()
    return resolved


AuthUser = Annotated[SessionUser, Depends(authenticated_user)]


async def current_user(user: AuthUser) -> RequestUser:
    """El usuario tal como lo miran las reglas de negocio, sin acoplarlas al modelo."""

    return RequestUser(role=user.role.value, name=user.full_name, id=user.id)


CurrentUser = Annotated[RequestUser, Depends(current_user)]


async def enforce_permissions(request: Request, user: AuthUser) -> SessionUser:
    """Permiso que pide la ruta que se acaba de resolver, según la tabla de autorización.

    Va como dependencia de todos los routers salvo el de sesión: una sola puerta en vez de
    un decorador por endpoint, y lo que no esté en la tabla queda para administración.
    """

    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path).removeprefix(settings.api_v1_prefix)

    required = permission_for(request.method, path)
    if required is None:
        return user
    if required not in permissions_of(user.role):
        raise DomainError(
            f"Su usuario no tiene permiso para esta operación ({required.value})",
            403,
        )
    return user


def requires(*permissions: Permission) -> Callable[..., SessionUser]:
    """Exige permisos en un endpoint puntual, para los que no pasan por la tabla."""

    async def guard(user: AuthUser) -> SessionUser:
        granted = permissions_of(user.role)
        missing = [permission for permission in permissions if permission not in granted]
        if missing:
            raise DomainError(
                "Su usuario no tiene permiso para esta operación: "
                + ", ".join(permission.value for permission in missing),
                403,
            )
        return user

    return guard


def request_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")
