"""SSE building blocks: the pub/sub multiplex hub and the draft buffer that
powers catch-up on reconnect.

The HTTP /stream endpoint itself is a thin relay over these two; it is verified
end-to-end against the live stack (httpx's ASGITransport buffers responses, so
it cannot exercise an unbounded SSE stream in-process).
"""
import asyncio
import contextlib

import app.worker as worker_mod
from app import redis_bus
from app.config import settings
from app.mockllm import POOLS
from app.sse_hub import PubSubHub

from .helpers import make_session, send, wait_until


async def test_hub_multiplexes_and_unsubscribes(r):
    # One hub connection, multiple in-memory subscribers per channel (this is
    # what makes Redis connections O(replicas) not O(streams)).
    client = redis_bus.make_redis()
    hub = PubSubHub(client)
    ch = redis_bus.tokens_channel("sess-x")
    try:
        q1 = await hub.subscribe(ch)
        q2 = await hub.subscribe(ch)
        await asyncio.sleep(0.05)

        await r.publish(ch, "frame-1")
        assert await asyncio.wait_for(q1.get(), timeout=2) == "frame-1"
        assert await asyncio.wait_for(q2.get(), timeout=2) == "frame-1"

        # After everyone unsubscribes, the channel is dropped: no more delivery.
        await hub.unsubscribe(ch, q1)
        await hub.unsubscribe(ch, q2)
        await asyncio.sleep(0.05)
        await r.publish(ch, "frame-2")
        await asyncio.sleep(0.1)
        assert q1.empty() and q2.empty()
    finally:
        await hub.close()
        await client.aclose()


async def test_draft_buffer_holds_partial_for_catchup(client, r, monkeypatch):
    # Slow the tokens so we can reliably observe a partial mid-generation: this
    # is exactly what a reconnecting SSE client replays as the catch-up frame.
    monkeypatch.setattr(settings, "token_min_delay", 0.03)
    monkeypatch.setattr(settings, "token_max_delay", 0.05)

    sid = await make_session(client)
    amid = (await send(client, sid, "explain scaling")).json()["assistant_message_id"]
    task = asyncio.create_task(
        worker_mod.handle_job(r, {"session_id": sid, "assistant_message_id": amid})
    )
    try:
        async def _partial():
            d = await r.hgetall(redis_bus.draft_key(amid))
            return d.get("text") if d else None

        partial = await wait_until(_partial, timeout=5)
        # The buffered partial is an exact prefix of the generated reply.
        assert partial and POOLS["default"].startswith(partial)
        assert len(partial) < len(POOLS["default"])  # genuinely partial
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
