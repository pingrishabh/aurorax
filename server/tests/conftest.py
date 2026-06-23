"""Shared fixtures for the backend test suite.

Tests run against a REAL Redis and Postgres (the things being tested are
durability, pub/sub, consumer groups, and the steer gate, none of which can be
faithfully mocked). The mock-LLM timing is sped up via env so generations finish
in milliseconds. Run hermetically with docker-compose.test.yml, or locally
against a Redis/Postgres you expose (see README).
"""
from __future__ import annotations

import asyncio
import contextlib
import os

import pytest_asyncio

# Fast mock-LLM timing + isolated Redis DB. Set BEFORE importing app modules so
# settings pick them up. A small-but-measurable think gap keeps the
# "thinking-before-first-token" assertion reliable.
os.environ.setdefault("THINK_MIN_DELAY", "0.12")
os.environ.setdefault("THINK_MAX_DELAY", "0.18")
os.environ.setdefault("TOKEN_MIN_DELAY", "0")
os.environ.setdefault("TOKEN_MAX_DELAY", "0.002")
os.environ.setdefault("DB_NULLPOOL", "1")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://chat:chat@localhost:5432/chat"
)

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import redis_bus  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.sse_hub import PubSubHub  # noqa: E402
import app.worker as worker_mod  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _clean():
    """Fresh schema + empty Redis + empty tables before every test."""
    await init_db()  # idempotent create_all
    r = redis_bus.make_redis()
    await r.flushdb()
    await redis_bus.ensure_group(r)
    await r.aclose()
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE sessions CASCADE"))
    yield


@pytest_asyncio.fixture
async def r():
    client = redis_bus.make_redis()
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def client():
    """httpx client wired to the FastAPI app, with the pub/sub hub running."""
    app.state.redis = redis_bus.make_redis()
    app.state.hub = PubSubHub(app.state.redis)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await app.state.hub.close()
    await app.state.redis.aclose()


@pytest_asyncio.fixture
async def worker():
    """Run a real worker loop in the background for the duration of a test."""
    task = asyncio.create_task(worker_mod.run())
    yield worker_mod
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task
