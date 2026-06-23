"""Worker generation behaviours: completion, the thinking gap, steer restart,
cancel, and last-steer-wins. Steer/cancel are driven deterministically by
pre-seeding the durable Redis structures the worker drains on pickup.
"""
import asyncio
import contextlib
import json
import time

import app.worker as worker_mod
from app import redis_bus

from .helpers import assistant_of, make_session, send, wait_until

HAIKU_MARK = "Quiet morning"  # appears only in the haiku pool


async def _capture(r, channel):
    ps = r.pubsub()
    await ps.subscribe(channel)
    frames: list[dict] = []

    async def loop():
        while True:
            msg = await ps.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if msg:
                frames.append(json.loads(msg["data"]))

    task = asyncio.create_task(loop())
    return ps, task, frames


async def test_generation_completes(client, worker):
    sid = await make_session(client)
    await send(client, sid, "explain horizontal scaling")

    async def _done():
        a = await assistant_of(client, sid)
        return a if a and a["status"] == "complete" else None

    a = await wait_until(_done)
    assert a["content"] and not a["steered"]


async def test_thinking_gap_before_first_token(client, worker, r):
    sid = await make_session(client)
    ps, task, frames = await _capture(r, redis_bus.tokens_channel(sid))
    await asyncio.sleep(0.02)  # ensure subscription is live before we send
    t0 = time.monotonic()
    await send(client, sid, "explain scaling")

    async def _first_token():
        for f in frames:
            if f["type"] == "token":
                return True
        return False

    await wait_until(_first_token, timeout=5)
    elapsed = time.monotonic() - t0
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await ps.aclose()
    # First token arrives only after the "thinking" pause (THINK_MIN_DELAY=0.12);
    # token pacing is ~0, so without the gap it would be near-instant.
    assert elapsed >= 0.08, f"first token too early ({elapsed:.3f}s), no think gap"


async def test_steer_restarts_and_switches_pool(client, r):
    sid = await make_session(client)
    amid = (await send(client, sid, "explain scaling")).json()["assistant_message_id"]
    # Pre-queue a steer; the worker applies it on the first loop iteration.
    await r.rpush(redis_bus.steerq_key(amid), "make it a haiku")

    ps, task, frames = await _capture(r, redis_bus.tokens_channel(sid))
    await asyncio.sleep(0.02)
    await worker_mod.handle_job(
        r, {"session_id": sid, "assistant_message_id": amid}
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await ps.aclose()

    types = [f["type"] for f in frames]
    assert "steered" in types and "reset" in types
    assert types[-1] == "done"
    a = await assistant_of(client, sid)
    assert a["status"] == "complete" and a["steered"] is True
    assert HAIKU_MARK in a["content"]


async def test_last_steer_wins(client, r):
    sid = await make_session(client)
    amid = (await send(client, sid, "explain scaling")).json()["assistant_message_id"]
    await r.rpush(redis_bus.steerq_key(amid), "make it concise")
    await r.rpush(redis_bus.steerq_key(amid), "make it a haiku")

    await worker_mod.handle_job(r, {"session_id": sid, "assistant_message_id": amid})
    a = await assistant_of(client, sid)
    assert HAIKU_MARK in a["content"]  # last steer (haiku), not concise


async def test_cancel_stops_generation(client, r):
    sid = await make_session(client)
    amid = (await send(client, sid, "explain scaling")).json()["assistant_message_id"]
    # Pre-set the cancel flag; the worker honours it on the first loop iteration.
    await r.set(redis_bus.cancel_key(amid), "1")

    await worker_mod.handle_job(r, {"session_id": sid, "assistant_message_id": amid})
    a = await assistant_of(client, sid)
    assert a["status"] == "cancelled"


async def test_keys_cleaned_up_after_generation(client, worker, r):
    sid = await make_session(client)
    amid = (await send(client, sid, "explain scaling")).json()["assistant_message_id"]

    async def _done():
        a = await assistant_of(client, sid)
        return a and a["status"] == "complete"

    await wait_until(_done)
    # active / draft / steerq / cancel keys are all removed on completion.
    assert await r.get(redis_bus.active_key(sid)) is None
    assert await r.exists(redis_bus.draft_key(amid)) == 0
    assert await r.exists(redis_bus.steerq_key(amid)) == 0
    assert await r.exists(redis_bus.cancel_key(amid)) == 0
