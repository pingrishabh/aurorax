"""FastAPI app, the stateless web tier.

Replicas of this process sit behind nginx. They own no in-memory chat state:
everything durable is in Postgres, everything live/coordinated is in Redis.
That is what lets us run N of them with no sticky sessions.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import redis_bus
from .config import settings
from .db import SessionLocal, init_db
from .models import Message, Session
from .sse_hub import PubSubHub
from .schemas import (
    MessageCreate,
    MessageOut,
    SendResult,
    SessionCreate,
    SessionOut,
    SessionRename,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = redis_bus.make_redis()
    # One shared pub/sub connection per api process, multiplexed across all of
    # this replica's SSE streams (so Redis connections scale O(replicas)).
    app.state.hub = PubSubHub(app.state.redis)
    await init_db()
    await redis_bus.ensure_group(app.state.redis)
    yield
    await app.state.hub.close()
    await app.state.redis.aclose()


app = FastAPI(title="Mock Chat API", lifespan=lifespan)

# Same-origin in Docker (nginx serves web + proxies /api). CORS is only needed
# for the optional local-dev path (vite on :5173 -> api on :8080).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_db() -> AsyncSession:
    async with SessionLocal() as db:
        yield db


def get_redis(request: Request):
    return request.app.state.redis


# --- health ----------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {"ok": True}


# --- sessions --------------------------------------------------------------
@app.get("/api/sessions", response_model=list[SessionOut])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Session).order_by(Session.updated_at.desc()))
    return list(rows.scalars())


@app.post("/api/sessions", response_model=SessionOut, status_code=201)
async def create_session(body: SessionCreate, db: AsyncSession = Depends(get_db)):
    session = Session(title=body.title or "New chat")
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@app.patch("/api/sessions/{session_id}", response_model=SessionOut)
async def rename_session(
    session_id: uuid.UUID, body: SessionRename, db: AsyncSession = Depends(get_db)
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(404, "session not found")
    session.title = body.title
    await db.commit()
    await db.refresh(session)
    return session


@app.delete("/api/sessions/{session_id}", status_code=204)
async def delete_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if session:
        await db.delete(session)
        await db.commit()
    return None


@app.get("/api/sessions/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    return list(rows.scalars())


# --- the core: non-blocking send + steering --------------------------------
@app.post(
    "/api/sessions/{session_id}/messages",
    response_model=SendResult,
    status_code=202,
)
async def send_message(
    session_id: uuid.UUID,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
    r=Depends(get_redis),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(404, "session not found")

    # Decide steer-vs-new with a single atomic gate: SET NX on the
    # active-generation marker. The winner starts a new turn; everyone else is
    # steering an in-progress reply. This is race-free across all api replicas.
    new_assistant_id = uuid.uuid4()
    won = await r.set(
        redis_bus.active_key(str(session_id)),
        str(new_assistant_id),
        nx=True,
        ex=settings.active_ttl,
    )
    active_id = None if won else await r.get(redis_bus.active_key(str(session_id)))
    # The turn this user message belongs to = the assistant reply's id (the new
    # one for a fresh turn, or the in-flight one being steered).
    turn_uuid = new_assistant_id if won else (
        uuid.UUID(active_id) if active_id else None
    )

    # Persist the user's message immediately (durable, survives reload).
    user_msg = Message(
        session_id=session_id,
        role="user",
        content=body.content,
        status="complete",
        turn_id=turn_uuid,
        is_steer=not won,
    )
    db.add(user_msg)
    if won and session.title == "New chat":
        session.title = body.content[:40]
    await db.commit()

    if not won:
        # A reply is in flight (or still queued) -> steer it. The instruction
        # goes to a DURABLE per-message list so it survives until a worker
        # actually picks the job up (e.g. across a worker outage), rather than
        # a fire-and-forget pub/sub message that a down worker would miss.
        if active_id:
            await r.rpush(redis_bus.steerq_key(active_id), body.content)
            await r.expire(redis_bus.steerq_key(active_id), settings.active_ttl)
            target = await db.get(Message, uuid.UUID(active_id))
            if target:
                target.steered = True
                await db.commit()
        return SendResult(steered=True, target_message_id=turn_uuid)

    # We own this turn: create the assistant placeholder and enqueue the job.
    assistant = Message(
        id=new_assistant_id,
        session_id=session_id,
        role="assistant",
        content="",
        status="pending",
        turn_id=new_assistant_id,
    )
    db.add(assistant)
    await db.commit()

    await r.xadd(
        redis_bus.REQUESTS_STREAM,
        {
            "session_id": str(session_id),
            "assistant_message_id": str(new_assistant_id),
            "user_message_id": str(user_msg.id),
        },
        maxlen=10_000,
        approximate=True,  # bound the stream so it can't grow without limit
    )
    return SendResult(steered=False, assistant_message_id=new_assistant_id)


@app.post("/api/sessions/{session_id}/cancel", status_code=202)
async def cancel(session_id: uuid.UUID, r=Depends(get_redis)):
    # Durable cancel flag on the active reply (polled by the worker), so it is
    # honoured even if set moments before a worker starts the job.
    active_id = await r.get(redis_bus.active_key(str(session_id)))
    if active_id:
        await r.set(redis_bus.cancel_key(active_id), "1", ex=settings.active_ttl)
    return {"cancelled": bool(active_id)}


# --- SSE: live tokens, reload-safe -----------------------------------------
def _sse(payload: str) -> str:
    return f"data: {payload}\n\n"


@app.get("/api/sessions/{session_id}/stream")
async def stream(session_id: uuid.UUID, request: Request, r=Depends(get_redis)):
    sid = str(session_id)
    hub: PubSubHub = request.app.state.hub

    async def event_gen():
        # Register on the shared per-process pub/sub BEFORE replaying the draft,
        # so we never miss tokens that land during catch-up (client de-dupes by
        # seq). No new Redis connection is opened here.
        q = await hub.subscribe(redis_bus.tokens_channel(sid))
        try:
            # Catch-up: if a reply is mid-flight, replay the partial first so a
            # reloaded tab immediately shows what it missed.
            active_id = await r.get(redis_bus.active_key(sid))
            if active_id:
                draft = await r.hgetall(redis_bus.draft_key(active_id))
                if draft:
                    yield _sse(
                        json.dumps(
                            {
                                "type": "catchup",
                                "mid": active_id,
                                "text": draft.get("text", ""),
                                "seq": int(draft.get("seq", 0)),
                            }
                        )
                    )

            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"  # heartbeat keeps the connection open
                    continue
                yield _sse(data)
        finally:
            await hub.unsubscribe(redis_bus.tokens_channel(sid), q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # belt-and-braces vs proxy buffering
        },
    )
