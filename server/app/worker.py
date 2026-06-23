"""Worker — the generation tier.

Runs as its own process/container (no HTTP). N replicas share one Redis Stream
consumer group, so jobs load-balance across them automatically. Each worker:

  1. claims a generation job (XREADGROUP)
  2. streams mock tokens, publishing each to tokens:{sid}
  3. listens on steer:{sid} / control:{sid} and adapts or aborts in real time
  4. persists the final message to Postgres, then XACKs

A crashed worker drops nothing: its un-acked jobs are reclaimed via XAUTOCLAIM.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import socket
import uuid

from . import redis_bus
from .config import settings
from .db import SessionLocal, wait_for_db
from .mockllm import POOLS, select_pool, tokenize
from .models import Message

CONSUMER = f"worker-{socket.gethostname()}-{os.getpid()}"
IDLE_RECLAIM_MS = 30_000  # reclaim jobs abandoned by a dead worker after 30s


async def _set_status(amid: uuid.UUID, **fields) -> None:
    async with SessionLocal() as db:
        msg = await db.get(Message, amid)
        if not msg:
            return
        for k, v in fields.items():
            setattr(msg, k, v)
        await db.commit()


async def handle_job(r, fields: dict) -> None:
    sid = fields["session_id"]
    amid = fields["assistant_message_id"]
    amid_uuid = uuid.UUID(amid)

    await _set_status(amid_uuid, status="streaming")
    await r.set(redis_bus.active_key(sid), amid, ex=settings.active_ttl)

    parts: list[str] = []
    remaining = tokenize(POOLS["default"])
    seq = 0
    cancelled = False
    steered = False

    async def apply_steer(content: str) -> None:
        # Steering restarts the reply: badge it, clear what's been shown, pause
        # to "think", then regenerate in the new direction from scratch.
        nonlocal parts, remaining, steered
        steered = True
        pool = select_pool(content)
        await r.publish(
            redis_bus.tokens_channel(sid),
            json.dumps({"type": "steered", "mid": amid}),
        )
        await r.publish(
            redis_bus.tokens_channel(sid),
            json.dumps({"type": "reset", "mid": amid}),
        )
        parts = []
        await r.hset(redis_bus.draft_key(amid), mapping={"text": "", "seq": seq})
        await r.expire(redis_bus.draft_key(amid), settings.active_ttl)
        await asyncio.sleep(random.uniform(1.0, 1.8))  # "thinking"
        remaining = tokenize(POOLS[pool])

    try:
        while remaining:
            # Durable control: a cancel flag and a queue of steer instructions,
            # both polled here. Because they live in Redis (not pub/sub), a
            # steer/cancel issued while this reply was still QUEUED — e.g. during
            # a worker outage — is applied when the job is finally picked up,
            # instead of being silently dropped.
            if await r.get(redis_bus.cancel_key(amid)) is not None:
                cancelled = True
                break
            latest_steer = None
            while True:
                s = await r.lpop(redis_bus.steerq_key(amid))
                if s is None:
                    break
                latest_steer = s  # last instruction wins
            if latest_steer is not None:
                await apply_steer(latest_steer)
                continue

            tok = remaining.pop(0)
            parts.append(tok)
            frame = {"type": "token", "mid": amid, "text": tok, "seq": seq}
            seq += 1

            text_so_far = "".join(parts)
            # Draft buffer (TTL) powers SSE catch-up on reconnect/reload.
            await r.hset(
                redis_bus.draft_key(amid),
                mapping={"text": text_so_far, "seq": seq},
            )
            await r.expire(redis_bus.draft_key(amid), settings.active_ttl)
            # Heartbeat the active marker so it outlives a slow generation.
            await r.set(redis_bus.active_key(sid), amid, ex=settings.active_ttl)
            await r.publish(redis_bus.tokens_channel(sid), json.dumps(frame))

            await asyncio.sleep(
                random.uniform(settings.token_min_delay, settings.token_max_delay)
            )

        status = "cancelled" if cancelled else "complete"
        await _set_status(
            amid_uuid, content="".join(parts), status=status, steered=steered
        )
        await r.publish(
            redis_bus.tokens_channel(sid),
            json.dumps(
                {"type": "done", "mid": amid, "status": status, "steered": steered}
            ),
        )
    finally:
        await r.delete(redis_bus.draft_key(amid))
        await r.delete(redis_bus.active_key(sid))
        await r.delete(redis_bus.steerq_key(amid))
        await r.delete(redis_bus.cancel_key(amid))


async def _process(r, entry_id: str, fields: dict) -> None:
    try:
        await handle_job(r, fields)
    except Exception as exc:  # noqa: BLE001 - keep the worker alive
        print(f"[{CONSUMER}] job {entry_id} failed: {exc!r}", flush=True)
    finally:
        await r.xack(redis_bus.REQUESTS_STREAM, redis_bus.WORKERS_GROUP, entry_id)


async def run() -> None:
    r = redis_bus.make_redis()
    await wait_for_db()
    await redis_bus.ensure_group(r)
    print(f"[{CONSUMER}] ready", flush=True)

    while True:
        # First, reclaim any jobs abandoned by a crashed worker.
        try:
            _, claimed, _ = await r.xautoclaim(
                redis_bus.REQUESTS_STREAM,
                redis_bus.WORKERS_GROUP,
                CONSUMER,
                min_idle_time=IDLE_RECLAIM_MS,
                start_id="0-0",
                count=1,
            )
            for entry_id, fields in claimed:
                if fields:
                    await _process(r, entry_id, fields)
        except Exception as exc:  # noqa: BLE001
            print(f"[{CONSUMER}] reclaim error: {exc!r}", flush=True)

        # Then block for new work.
        resp = await r.xreadgroup(
            redis_bus.WORKERS_GROUP,
            CONSUMER,
            {redis_bus.REQUESTS_STREAM: ">"},
            count=1,
            block=5000,
        )
        if not resp:
            continue
        for _stream, entries in resp:
            for entry_id, fields in entries:
                await _process(r, entry_id, fields)


if __name__ == "__main__":
    asyncio.run(run())
