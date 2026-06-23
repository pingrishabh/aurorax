"""Worker, the generation tier.

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
MAX_DELIVERIES = 5  # dead-letter a job after this many failed attempts


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
        await _think()  # pause before regenerating
        remaining = tokenize(POOLS[pool])

    async def _think() -> None:
        await asyncio.sleep(
            random.uniform(settings.think_min_delay, settings.think_max_delay)
        )

    try:
        # Pause to "think" before the very first token, just like a steer does.
        # The UI shows a "Thinking" state (empty streaming reply) during this.
        await _think()
        while remaining:
            # Durable control: a cancel flag and a queue of steer instructions,
            # both polled here. Because they live in Redis (not pub/sub), a
            # steer/cancel issued while this reply was still QUEUED, e.g. during
            # a worker outage, is applied when the job is finally picked up,
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
        # Best-effort cleanup; never let a cleanup error mask a generation error
        # (which would otherwise swallow the failure and wrongly ack the job).
        for key in (
            redis_bus.draft_key(amid),
            redis_bus.active_key(sid),
            redis_bus.steerq_key(amid),
            redis_bus.cancel_key(amid),
        ):
            try:
                await r.delete(key)
            except Exception:  # noqa: BLE001
                pass


async def _delivery_count(r, entry_id: str) -> int:
    try:
        info = await r.xpending_range(
            redis_bus.REQUESTS_STREAM,
            redis_bus.WORKERS_GROUP,
            min=entry_id,
            max=entry_id,
            count=1,
        )
        return info[0]["times_delivered"] if info else 1
    except Exception:  # noqa: BLE001
        return 1


async def _process(r, entry_id: str, fields: dict) -> None:
    """Run a job, then XACK ONLY on success.

    A failure (DB/Redis blip) leaves the entry pending so it is retried later via
    XAUTOCLAIM, i.e. persist-then-ack: a generated reply is never acked until it
    is durably written. Poison jobs that keep failing are dead-lettered after
    MAX_DELIVERIES so they cannot loop forever.
    """
    if not fields:  # tombstone (trimmed/deleted entry)
        await r.xack(redis_bus.REQUESTS_STREAM, redis_bus.WORKERS_GROUP, entry_id)
        return
    try:
        await handle_job(r, fields)
    except Exception as exc:  # noqa: BLE001
        if await _delivery_count(r, entry_id) >= MAX_DELIVERIES:
            print(
                f"[{CONSUMER}] job {entry_id} dead-lettered after retries: {exc!r}",
                flush=True,
            )
            # Best-effort: don't leave the reply stuck "thinking" on reload.
            try:
                await _set_status(
                    uuid.UUID(fields["assistant_message_id"]), status="cancelled"
                )
            except Exception:  # noqa: BLE001
                pass
            await r.xack(redis_bus.REQUESTS_STREAM, redis_bus.WORKERS_GROUP, entry_id)
        else:
            print(f"[{CONSUMER}] job {entry_id} failed, will retry: {exc!r}", flush=True)
        return
    await r.xack(redis_bus.REQUESTS_STREAM, redis_bus.WORKERS_GROUP, entry_id)


async def _drain_once(r) -> None:
    # Reclaim jobs abandoned by a crashed worker, then take new work.
    _, claimed, _ = await r.xautoclaim(
        redis_bus.REQUESTS_STREAM,
        redis_bus.WORKERS_GROUP,
        CONSUMER,
        min_idle_time=IDLE_RECLAIM_MS,
        start_id="0-0",
        count=10,
    )
    for entry_id, fields in claimed:
        await _process(r, entry_id, fields)

    resp = await r.xreadgroup(
        redis_bus.WORKERS_GROUP,
        CONSUMER,
        {redis_bus.REQUESTS_STREAM: ">"},
        count=1,
        block=5000,
    )
    for _stream, entries in resp or []:
        for entry_id, fields in entries:
            await _process(r, entry_id, fields)


async def run() -> None:
    r = redis_bus.make_redis()
    await wait_for_db()
    await redis_bus.ensure_group(r)
    print(f"[{CONSUMER}] ready", flush=True)

    # Survive Redis/DB blips instead of crashing the process: on error, back off
    # and retry. With `restart: unless-stopped` this is belt-and-braces, the loop
    # reconnects without even losing the process.
    backoff = 1.0
    while True:
        try:
            await _drain_once(r)
            backoff = 1.0
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            print(
                f"[{CONSUMER}] loop error ({exc!r}); reconnecting in {backoff:.0f}s",
                flush=True,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 10.0)
            # Redis may have restarted and lost the group; recreate (idempotent).
            try:
                await redis_bus.ensure_group(r)
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    asyncio.run(run())
