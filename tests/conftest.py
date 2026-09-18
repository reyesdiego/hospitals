"""PostgreSQL harness for the integration tests.

Database specific behaviour (partial unique indexes, SELECT FOR UPDATE) cannot be
exercised without PostgreSQL, so these tests run against a dedicated database and are
skipped when the server configured in the settings is not reachable.
"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base

TEST_DATABASE = os.getenv("HOSPITAL_TEST_DB", f"{settings.postgres_db}_test")
_SERVER_URL = settings.database_url.rsplit("/", 1)[0]
TEST_DATABASE_URL = f"{_SERVER_URL}/{TEST_DATABASE}"
ADMIN_DATABASE_URL = f"{_SERVER_URL}/postgres"

SessionFactory = async_sessionmaker[AsyncSession]

_schema_ready = False
_postgres_available: bool | None = None


async def _create_schema() -> None:
    admin = create_async_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DATABASE},
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{TEST_DATABASE}"'))
    finally:
        await admin.dispose()

    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


async def _truncate(engine) -> None:
    tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


def postgres_available() -> bool:
    global _postgres_available
    if _postgres_available is None:
        async def probe() -> bool:
            admin = create_async_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
            try:
                async with admin.connect() as connection:
                    await connection.scalar(text("SELECT 1"))
                return True
            except (OSError, SQLAlchemyError):
                return False
            finally:
                await admin.dispose()

        _postgres_available = asyncio.run(probe())
    return _postgres_available


def run_db(case: Callable[[SessionFactory], Awaitable[Any]]) -> Any:
    """Run ``case`` against a clean test database and return its result."""

    async def main() -> Any:
        global _schema_ready
        if not _schema_ready:
            await _create_schema()
            _schema_ready = True
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            await _truncate(engine)
            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            return await case(factory)
        finally:
            await engine.dispose()

    return asyncio.run(main())


requires_postgres = pytest.mark.skipif(
    not postgres_available(),
    reason="PostgreSQL no disponible para pruebas de integración",
)
