from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class DomainError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message, self.status_code = message, status_code
        super().__init__(message)


@asynccontextmanager
async def integrity_conflict(
    session: AsyncSession,
    message: str,
    status_code: int = 409,
) -> AsyncIterator[None]:
    """Translate a database conflict into a domain error instead of leaking PostgreSQL."""

    try:
        yield
    except IntegrityError as exc:
        await session.rollback()
        raise DomainError(message, status_code) from exc


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})
