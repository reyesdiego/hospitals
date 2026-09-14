from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import settings
from app.db.base import Base

config=context.config; config.set_main_option("sqlalchemy.url",settings.database_url)
if config.config_file_name: fileConfig(config.config_file_name)
target_metadata=Base.metadata
def do_run(connection):
    context.configure(connection=connection,target_metadata=target_metadata,compare_type=True)
    with context.begin_transaction(): context.run_migrations()
async def run_async():
    engine=async_engine_from_config(config.get_section(config.config_ini_section,{}),prefix="sqlalchemy.",poolclass=pool.NullPool)
    async with engine.connect() as connection: await connection.run_sync(do_run)
    await engine.dispose()
def run_migrations_online():
    import asyncio; asyncio.run(run_async())
run_migrations_online()
