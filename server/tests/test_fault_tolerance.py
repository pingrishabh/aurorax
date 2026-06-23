"""The ugly: worker outages, abandoned jobs, persist-then-ack, dead-lettering."""
import asyncio
import contextlib
import uuid

import app.worker as worker_mod
from app import redis_bus

from .helpers import assistant_of, make_session, send, wait_until


def _const(val):
    async def f(*_a, **_k):
        return val

    return f


async def _run_worker_briefly(coro_pred, timeout=10):
    task = asyncio.create_task(worker_mod.run())
    try:
        return await wait_until(coro_pred, timeout=timeout)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


async def test_jobs_durable_during_outage_then_drained(client, r):
    sid = await make_session(client)
    await send(client, sid, "hi there")  # no worker running

    # The job sits durably on the stream, undelivered (lag = 1).
    assert await r.xlen(redis_bus.REQUESTS_STREAM) == 1
    groups = await r.xinfo_groups(redis_bus.REQUESTS_STREAM)
    assert groups[0]["lag"] == 1
    assert (await assistant_of(client, sid))["status"] == "pending"

    # Bring a worker up -> it drains the backlog and completes the reply.
    async def _done():
        a = await assistant_of(client, sid)
        return a and a["status"] == "complete" and a["content"]

    await _run_worker_briefly(_done)


async def test_steer_survives_worker_outage(client, r):
    sid = await make_session(client)
    amid = (await send(client, sid, "explain scaling")).json()["assistant_message_id"]
    await send(client, sid, "make it a haiku")  # steers while worker is down

    # The steer is durably queued (not a lost pub/sub message).
    assert await r.lrange(redis_bus.steerq_key(amid), 0, -1) == ["make it a haiku"]

    async def _haiku():
        a = await assistant_of(client, sid)
        return (
            a
            and a["status"] == "complete"
            and a["steered"]
            and "Quiet morning" in a["content"]
        )

    await _run_worker_briefly(_haiku)


async def test_abandoned_job_is_reclaimed(client, r, monkeypatch):
    monkeypatch.setattr(worker_mod, "IDLE_RECLAIM_MS", 100)
    sid = await make_session(client)
    await send(client, sid, "explain scaling")

    # Simulate a worker that read the job into its PEL then crashed (no ack).
    await r.xreadgroup(
        redis_bus.WORKERS_GROUP,
        "dead-worker",
        {redis_bus.REQUESTS_STREAM: ">"},
        count=1,
    )
    pending = await r.xpending(redis_bus.REQUESTS_STREAM, redis_bus.WORKERS_GROUP)
    assert pending["pending"] == 1
    await asyncio.sleep(0.15)  # age the entry past the reclaim idle threshold

    # A live worker reclaims via XAUTOCLAIM and completes the reply.
    async def _done():
        a = await assistant_of(client, sid)
        return a and a["status"] == "complete" and a["content"]

    await _run_worker_briefly(_done, timeout=12)


async def test_no_ack_on_failure_so_job_is_retried(r, monkeypatch):
    # A job that fails (e.g. DB blip) must stay pending, not be acked-and-lost.
    sid, amid = str(uuid.uuid4()), str(uuid.uuid4())
    await r.xadd(
        redis_bus.REQUESTS_STREAM,
        {"session_id": sid, "assistant_message_id": amid},
    )
    resp = await r.xreadgroup(
        redis_bus.WORKERS_GROUP,
        worker_mod.CONSUMER,
        {redis_bus.REQUESTS_STREAM: ">"},
        count=1,
    )
    entry_id = resp[0][1][0][0]

    async def boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(worker_mod, "handle_job", boom)
    monkeypatch.setattr(worker_mod, "_delivery_count", _const(1))

    await worker_mod._process(r, entry_id, {"session_id": sid, "assistant_message_id": amid})
    pending = await r.xpending(redis_bus.REQUESTS_STREAM, redis_bus.WORKERS_GROUP)
    assert pending["pending"] == 1  # NOT acked -> will be retried


async def test_dead_letter_after_max_deliveries(client, r, monkeypatch):
    sid = await make_session(client)
    amid = (await send(client, sid, "explain scaling")).json()["assistant_message_id"]
    resp = await r.xreadgroup(
        redis_bus.WORKERS_GROUP,
        worker_mod.CONSUMER,
        {redis_bus.REQUESTS_STREAM: ">"},
        count=1,
    )
    entry_id = resp[0][1][0][0]

    async def boom(*_a, **_k):
        raise RuntimeError("persistent poison")

    monkeypatch.setattr(worker_mod, "handle_job", boom)
    monkeypatch.setattr(worker_mod, "_delivery_count", _const(worker_mod.MAX_DELIVERIES))

    await worker_mod._process(r, entry_id, {"session_id": sid, "assistant_message_id": amid})

    pending = await r.xpending(redis_bus.REQUESTS_STREAM, redis_bus.WORKERS_GROUP)
    assert pending["pending"] == 0  # acked (dead-lettered, no infinite loop)
    # The reply is marked so the UI doesn't hang on "thinking" forever.
    assert (await assistant_of(client, sid))["status"] == "cancelled"
