"""Runtime configuration, read from environment variables.

Every process (api replicas + worker replicas) reads the same two connection
strings. Nothing else is configurable on purpose: the only stateful backends
are Postgres and Redis.
"""
from __future__ import annotations

import os


class Settings:
    # Postgres: durable source of truth (sessions + message history).
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://chat:chat@postgres:5432/chat",
    )
    # Redis: work queue (Streams) + live fan-out / steering / cancel (Pub/Sub)
    # + draft buffer + active-generation registry.
    redis_url: str = os.environ.get("REDIS_URL", "redis://redis:6379/0")

    # Mock-LLM token pacing (seconds). Randomised per token to look like typing.
    token_min_delay: float = float(os.environ.get("TOKEN_MIN_DELAY", "0.03"))
    token_max_delay: float = float(os.environ.get("TOKEN_MAX_DELAY", "0.12"))

    # "Thinking" pause (seconds) before the first token of a reply, and again
    # after a steer restarts generation. Makes the assistant feel like it pauses
    # to consider before answering.
    think_min_delay: float = float(os.environ.get("THINK_MIN_DELAY", "0.8"))
    think_max_delay: float = float(os.environ.get("THINK_MAX_DELAY", "1.6"))

    # How long an "active generation" marker / draft buffer lives without a
    # heartbeat before Redis expires it (seconds).
    active_ttl: int = int(os.environ.get("ACTIVE_TTL", "60"))


settings = Settings()
