"""Redis wiring: the coordination layer that makes the system horizontally
scalable.

Each structure below has a single, deliberate job (see ARCHITECTURE.md):

  - REQUESTS_STREAM  : durable work queue (Stream + consumer group). Lets the
                       api return 202 instantly and lets workers scale out.
  - tokens:{sid}     : Pub/Sub fan-out of generated tokens -> whichever
                       stateless api replica holds the browser's SSE socket.
  - steerq:{mid}     : durable LIST of pending steer instructions for a reply.
                       The worker drains it when it STARTS the job and on every
                       token, so a steer issued while the reply is still queued
                       (e.g. during a worker outage) is applied, not lost.
  - cancel:{mid}     : durable flag (TTL) requesting cancel of a reply; polled
                       by the worker. Same reasoning as steerq.
  - draft:{mid}      : string buffer of the partial reply (TTL) so a reloaded
                       SSE connection can catch up before subscribing live.
  - gen:active:{sid} : marks that a generation is in flight (value = assistant
                       message id, TTL+heartbeat) so any replica can decide
                       steer-vs-new-turn.
"""
from __future__ import annotations

import redis.asyncio as redis

from .config import settings

REQUESTS_STREAM = "gen:requests"
WORKERS_GROUP = "workers"


def make_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


# --- channel / key name builders -------------------------------------------
def tokens_channel(session_id: str) -> str:
    return f"tokens:{session_id}"


def steerq_key(message_id: str) -> str:
    return f"steerq:{message_id}"


def cancel_key(message_id: str) -> str:
    return f"cancel:{message_id}"


def draft_key(message_id: str) -> str:
    return f"draft:{message_id}"


def active_key(session_id: str) -> str:
    return f"gen:active:{session_id}"


async def ensure_group(r: redis.Redis) -> None:
    """Create the consumer group if it does not exist (idempotent)."""
    try:
        await r.xgroup_create(REQUESTS_STREAM, WORKERS_GROUP, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
