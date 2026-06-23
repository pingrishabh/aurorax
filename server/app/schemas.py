"""Pydantic request/response shapes for the HTTP API."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class SessionCreate(BaseModel):
    title: str | None = None


class SessionRename(BaseModel):
    title: str


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
    content: str = Field(min_length=1)


class SendResult(BaseModel):
    # Returned immediately (HTTP 202). Either a new assistant turn was queued,
    # or the message steered an in-progress reply.
    steered: bool
    assistant_message_id: uuid.UUID | None = None
    target_message_id: uuid.UUID | None = None
