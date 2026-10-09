"""Outbox writer. Services emit events in the same transaction as the change they describe."""

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.notifications.models import OutboxEvent

EVENT_TYPES = frozenset(
    {
        "invoice.confirmation_requested",
        "invoice.confirmed",
        "invoice.disputed",
        "window.frozen",
        "run.computed",
        "run.statements_issued",
        "run.approval_received",
        "run.funding_failed",
        "run.recomputed",
        "run.committed",
        "run.aborted",
        "run.fallback_gross",
    }
)


def emit(session: Session, event_type: str, aggregate_id: UUID, payload: dict[str, Any]) -> None:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event type {event_type}")
    session.add(OutboxEvent(type=event_type, aggregate_id=aggregate_id, payload=payload))
