"""Test helpers shared across modules (fixtures live in conftest.py)."""
from __future__ import annotations

import asyncio
import time


async def make_session(client) -> str:
    resp = await client.post("/api/sessions", json={})
    assert resp.status_code == 201
    return resp.json()["id"]


async def send(client, sid: str, content: str):
    return await client.post(f"/api/sessions/{sid}/messages", json={"content": content})


async def get_messages(client, sid: str):
    resp = await client.get(f"/api/sessions/{sid}/messages")
    assert resp.status_code == 200
    return resp.json()


async def assistant_of(client, sid: str):
    msgs = await get_messages(client, sid)
    a = [m for m in msgs if m["role"] == "assistant"]
    return a[0] if a else None


async def wait_until(pred, timeout: float = 10.0, interval: float = 0.05):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = await pred()
        if last:
            return last
        await asyncio.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s (last={last!r})")
