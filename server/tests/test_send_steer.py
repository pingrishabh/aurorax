"""Non-blocking send + the steer-vs-new gate + turn grouping.

The gate is deterministic without a worker: the api sets `gen:active` (SET NX)
synchronously before returning, so a second send always classifies as a steer
until the reply finishes.
"""
from app import redis_bus

from .helpers import get_messages, make_session, send, wait_until


async def test_send_is_non_blocking_202(client):
    sid = await make_session(client)
    resp = await send(client, sid, "hello")
    assert resp.status_code == 202
    body = resp.json()
    assert body["steered"] is False
    assert body["assistant_message_id"]
    assert body["target_message_id"] is None


async def test_second_message_steers_in_flight_reply(client):
    sid = await make_session(client)
    r1 = (await send(client, sid, "explain scaling")).json()
    r2 = (await send(client, sid, "make it a haiku")).json()
    assert r1["steered"] is False
    assert r2["steered"] is True
    assert r2["target_message_id"] == r1["assistant_message_id"]


async def test_steer_does_not_enqueue_second_job_and_is_durable(client, r):
    sid = await make_session(client)
    amid = (await send(client, sid, "first")).json()["assistant_message_id"]
    await send(client, sid, "make it a haiku")
    # Only the first turn enqueued a job; the steer did not.
    assert await r.xlen(redis_bus.REQUESTS_STREAM) == 1
    # The steer instruction is durably queued for the worker (survives outage).
    assert await r.lrange(redis_bus.steerq_key(amid), 0, -1) == ["make it a haiku"]


async def test_turn_grouping_fields(client):
    sid = await make_session(client)
    amid = (await send(client, sid, "main prompt")).json()["assistant_message_id"]
    await send(client, sid, "steer one")
    await send(client, sid, "steer two")

    msgs = await get_messages(client, sid)
    users = [m for m in msgs if m["role"] == "user"]
    assistants = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistants) == 1
    asst = assistants[0]

    main = [u for u in users if not u["is_steer"]]
    steers = [u for u in users if u["is_steer"]]
    # One main prompt, two steers, all sharing the assistant reply's turn_id.
    assert len(main) == 1 and main[0]["turn_id"] == amid
    assert len(steers) == 2 and all(s["turn_id"] == amid for s in steers)
    assert asst["turn_id"] == amid
    # The gate flags the reply as steered as soon as a steer arrives.
    assert asst["steered"] is True


async def test_new_turn_after_previous_completes(client, worker):
    sid = await make_session(client)
    a1 = (await send(client, sid, "first")).json()["assistant_message_id"]

    async def _done():
        msgs = await get_messages(client, sid)
        m = next((x for x in msgs if x["id"] == a1), None)
        return m and m["status"] == "complete"

    await wait_until(_done)
    # Active marker cleared on completion -> the next send starts a NEW turn.
    r2 = (await send(client, sid, "second")).json()
    assert r2["steered"] is False
    assert r2["assistant_message_id"] != a1
