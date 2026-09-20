"""Esquemas de autenticación y usuarios."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.permissions import Permission, UserRole


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EmailField(BaseModel):
    """Validación mínima del correo: no vale la pena una dependencia para esto, y quien
    manda el alta es un administrador, no un formulario público."""

    email: str = Field(min_length=3, max_length=180)

    @field_validator("email")
    @classmethod
    def looks_like_an_email(cls, value: str) -> str:
        value = value.strip().lower()
        local, _, domain = value.partition("@")
        if not local or not domain or "." not in domain or " " in value:
            raise ValueError("El correo no tiene un formato válido")
        return value


class LoginRequest(EmailField):
    password: str = Field(min_length=1, max_length=128)


class UserRead(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class SessionRead(BaseModel):
    """Lo que necesita el cliente para operar: quién es y qué puede hacer."""

    token: str
    expires_at: datetime
    user: UserRead
    permissions: list[Permission]


class CurrentUserRead(BaseModel):
    user: UserRead
    permissions: list[Permission]


class UserCreate(EmailField):
    full_name: str = Field(min_length=1, max_length=150)
    role: UserRole
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True


class UserUpdate(EmailField):
    """``password`` vacío deja la que tenía."""

    full_name: str = Field(min_length=1, max_length=150)
    role: UserRole
    is_active: bool = True
    password: str | None = Field(default=None, min_length=8, max_length=128)
