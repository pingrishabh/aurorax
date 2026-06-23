"""Concurrency: the steer-vs-new gate under simultaneous sends."""
import asyncio

from .helpers import make_session, send


async def test_simultaneous_sends_one_session_single_winner(client):
    sid = await make_session(client)
    # Fire many sends at once; the SET NX gate must pick exactly one new turn.
    results = await asyncio.gather(*[send(client, sid, f"m{i}") for i in range(12)])
    bodies = [r.json() for r in results]

    winners = [b for b in bodies if b["steered"] is False]
    steers = [b for b in bodies if b["steered"] is True]
    assert len(winners) == 1, f"expected exactly 1 new turn, got {len(winners)}"
    assert len(steers) == 11
    # Every steer targets the single winning reply.
    amid = winners[0]["assistant_message_id"]
    assert all(b["target_message_id"] == amid for b in steers)


async def test_simultaneous_sends_across_sessions_all_new_turns(client):
    sids = [await make_session(client) for _ in range(15)]
    results = await asyncio.gather(*[send(client, s, "hi") for s in sids])
    # Each session has its own gate, so every first send starts its own turn.
    assert all(r.status_code == 202 for r in results)
    assert all(r.json()["steered"] is False for r in results)
