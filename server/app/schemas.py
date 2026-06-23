"""Pydantic request/response shapes for the HTTP API.

Request models bound user text so hostile or accidental inputs become clean
422s, not 500s: length caps (Postgres `varchar(200)` titles, a generous message
cap) and NUL stripping (Postgres TEXT cannot store NUL bytes).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

TITLE_MAX = 200
CONTENT_MAX = 8000


def _strip_nul(v):
    return v.replace("\x00", "") if isinstance(v, str) else v


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=TITLE_MAX)

    _clean = field_validator("title", mode="before")(_strip_nul)


class SessionRename(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)

    _clean = field_validator("title", mode="before")(_strip_nul)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    status: str
    steered: bool
    turn_id: uuid.UUID | None = None
    is_steer: bool = False
    created_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=CONTENT_MAX)

    _clean = field_validator("content", mode="before")(_strip_nul)


class SendResult(BaseModel):
    # Returned immediately (HTTP 202). Either a new assistant turn was queued,
    # or the message steered an in-progress reply.
    steered: bool
    assistant_message_id: uuid.UUID | None = None
    target_message_id: uuid.UUID | None = None
