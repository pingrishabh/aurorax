"""Per-process pub/sub multiplexer for SSE.

Without this, every SSE stream opens its own Redis pub/sub connection, so Redis
connections grow O(active streams). That caps how many concurrent viewers a
single api replica can serve before exhausting Redis/OS connections.

Instead, each api process keeps ONE Redis pub/sub connection. A single reader
task owns that connection; SSE streams register an in-memory asyncio.Queue per
channel. Channels are reference-counted: the first subscriber issues SUBSCRIBE,
the last to leave issues UNSUBSCRIBE. Redis connections become O(api replicas),
not O(streams), which is what lets the streaming tier scale out.

A single asyncio.Lock serializes all access to the shared pub/sub connection
(redis-py's PubSub is not safe for concurrent use from multiple tasks).
"""
from __future__ import annotations

import asyncio


class PubSubHub:
    def __init__(self, redis) -> None:
        self._pubsub = redis.pubsub()
        self._lock = asyncio.Lock()
        self._channels: dict[str, set[asyncio.Queue]] = {}
        self._reader: asyncio.Task | None = None
        self._closed = False

    async def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            subs = self._channels.get(channel)
            if subs is None:
                subs = set()
                self._channels[channel] = subs
                await self._pubsub.subscribe(channel)
            subs.add(q)
            if self._reader is None or self._reader.done():
                self._reader = asyncio.create_task(self._read_loop())
        return q

    async def unsubscribe(self, channel: str, q: asyncio.Queue) -> None:
        async with self._lock:
            subs = self._channels.get(channel)
            if not subs:
                return
            subs.discard(q)
            if not subs:
                del self._channels[channel]
                try:
                    await self._pubsub.unsubscribe(channel)
                except Exception:  # noqa: BLE001
                    pass

    async def _read_loop(self) -> None:
        while not self._closed:
            try:
                async with self._lock:
                    msg = await self._pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=0.1
                    )
            except Exception:  # noqa: BLE001 - survive Redis blips
                await asyncio.sleep(0.5)
                continue
            if msg is None:
                await asyncio.sleep(0)  # yield so subscribe()/unsubscribe() run
                continue
            # Fan out to every SSE stream registered on this channel.
            for q in tuple(self._channels.get(msg["channel"], ())):
                q.put_nowait(msg["data"])

    async def close(self) -> None:
        self._closed = True
        if self._reader:
            self._reader.cancel()
        try:
            await self._pubsub.aclose()
        except Exception:  # noqa: BLE001
            pass
