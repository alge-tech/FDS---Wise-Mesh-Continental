from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.db import Base, fk, pk, timestamp_col


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[UUID] = pk()
    user_id: Mapped[UUID] = fk("users.id")
    event_id: Mapped[UUID] = fk("outbox_events.id", index=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    read_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = timestamp_col()

    # Handlers are idempotent on event ID: one notification per user per event.
    __table_args__ = (UniqueConstraint("event_id", "user_id"),)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[UUID] = pk()
    type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = timestamp_col()
    processed_at: Mapped[datetime | None] = mapped_column(index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
