"""Inicio de sesión y administración de usuarios."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import (
    AuthUser,
    DbSession,
    bearer_token,
    request_user_agent,
    requires,
)
from app.core.permissions import Permission, permissions_of
from app.schemas.auth import (
    CurrentUserRead,
    LoginRequest,
    SessionRead,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.services.auth import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=SessionRead)
async def login(
    payload: LoginRequest,
    session: DbSession,
    user_agent: Annotated[str | None, Depends(request_user_agent)],
):
    """Devuelve el token de la sesión y lo que el usuario puede hacer."""

    user, token, expires_at = await AuthService(session).login(
        payload.email, payload.password, user_agent=user_agent
    )
    return SessionRead(
        token=token,
        expires_at=expires_at,
        user=UserRead.model_validate(user),
        permissions=sorted(permissions_of(user.role), key=lambda item: item.value),
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(session: DbSession, token: Annotated[str, Depends(bearer_token)]):
    await AuthService(session).logout(token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/me", response_model=CurrentUserRead)
async def me(user: AuthUser):
    return CurrentUserRead(user=UserRead.model_validate(user), permissions=user.permissions)


@router.get(
    "/users",
    response_model=list[UserRead],
    dependencies=[Depends(requires(Permission.USER_ADMIN))],
)
async def list_users(session: DbSession):
    return await AuthService(session).list_users()


@router.post(
    "/users",
    response_model=UserRead,
    status_code=201,
    dependencies=[Depends(requires(Permission.USER_ADMIN))],
)
async def create_user(payload: UserCreate, session: DbSession):
    return await AuthService(session).create_user(payload)


@router.put(
    "/users/{user_id}",
    response_model=UserRead,
    dependencies=[Depends(requires(Permission.USER_ADMIN))],
)
async def update_user(user_id: uuid.UUID, payload: UserUpdate, session: DbSession):
    """Cambiar el rol, dar de baja o cambiar la contraseña cierra las sesiones abiertas."""

    return await AuthService(session).update_user(user_id, payload)
