from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.db import Base, fk, pk, timestamp_col


class AuditEvent(Base):
    """Insert-only record of every state change and every Wise staff action."""

    __tablename__ = "audit_events"

    id: Mapped[UUID] = pk()
    actor_id: Mapped[UUID | None] = fk("users.id", nullable=True)
    actor_role: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    run_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    before_hash: Mapped[str | None] = mapped_column(Text)
    after_hash: Mapped[str | None] = mapped_column(Text)
    reason_code: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = timestamp_col()


class IdempotencyKey(Base):
    """Stored response for an Idempotency-Key, written in the same transaction as the change."""

    __tablename__ = "idempotency_keys"

    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response: Mapped[Any] = mapped_column(JSONB)
    created_at: Mapped[datetime] = timestamp_col()
