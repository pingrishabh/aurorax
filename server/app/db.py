"""Async SQLAlchemy engine + session factory.

Postgres is the durable source of truth. Both the api and the worker import
from here so the schema and access patterns are shared.
"""
from __future__ import annotations

import asyncio
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from .config import settings
from .models import Base

# Tests run each case on a fresh event loop; an asyncpg connection is bound to
# the loop that created it, so reusing a pooled one across loops fails. NullPool
# (opt-in via env) opens a fresh connection per operation to sidestep that.
if os.environ.get("DB_NULLPOOL") == "1":
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
else:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db(retries: int = 30, delay: float = 1.0) -> None:
    """Create tables, retrying until Postgres is reachable.

    All api replicas may run this concurrently on boot; create_all uses
    checkfirst so it is idempotent. We retry to ride out the DB container
    still starting up.
    """
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except Exception as exc:  # noqa: BLE001 - boot-time connection churn
            last_err = exc
            await asyncio.sleep(delay)
    raise RuntimeError(f"database not ready after retries: {last_err}")


async def wait_for_db(retries: int = 60, delay: float = 1.0) -> None:
    """Block until a trivial query succeeds (used by the worker on boot)."""
    from sqlalchemy import text

    last_err: Exception | None = None
    for _ in range(retries):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            await asyncio.sleep(delay)
    raise RuntimeError(f"database not ready after retries: {last_err}")
