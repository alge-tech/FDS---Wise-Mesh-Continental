"""In-process outbox worker, started in the FastAPI lifespan.

It polls unprocessed events every second, claims them with FOR UPDATE SKIP LOCKED and
turns them into in-app notifications. Handlers are idempotent on event ID: a notification
is unique per (event, user), so re-processing an event never duplicates anything.
"""

import asyncio
import contextlib
from collections.abc import Callable

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import session_factory
from app.core.enums import Role
from app.core.ids import new_id, utcnow
from app.modules.members.models import User
from app.modules.notifications.models import Notification, OutboxEvent

log = structlog.get_logger()
MAX_ATTEMPTS = 5

# event type -> (notification type, roles to notify or None for every user of the member)
NOTIFY: dict[str, tuple[str, frozenset[Role] | None]] = {
    "invoice.confirmation_requested": (
        "CONFIRMATION_REQUEST",
        frozenset({Role.MEMBER_ADMIN, Role.FINANCE_USER}),
    ),
    "invoice.disputed": ("INVOICE_DISPUTED", frozenset({Role.MEMBER_ADMIN, Role.FINANCE_USER})),
    "run.statements_issued": ("STATEMENT_READY", None),
    "run.recomputed": ("RECOMPUTATION", None),
    "run.funding_failed": ("FUNDING_NEEDED", frozenset({Role.MEMBER_ADMIN, Role.FINANCE_USER})),
    "run.committed": ("SETTLEMENT_DONE", None),
    "run.aborted": ("RUN_ABORTED", None),
    "run.fallback_gross": ("RUN_FALLBACK", None),
}


def _notify(session: Session, event: OutboxEvent) -> None:
    spec = NOTIFY.get(event.type)
    if spec is None:
        return
    notification_type, roles = spec
    member_ids = event.payload.get("member_ids") or [event.payload["member_id"]]
    query = select(User.id).where(User.member_id.in_(member_ids))
    if roles is not None:
        query = query.where(User.role.in_([r.value for r in roles]))
    user_ids = session.scalars(query.order_by(User.id)).all()
    if not user_ids:
        return
    public_payload = {
        k: v for k, v in event.payload.items() if k not in ("member_ids", "member_id")
    }
    session.execute(
        pg_insert(Notification)
        .values(
            [
                {
                    "id": new_id(),
                    "user_id": uid,
                    "event_id": event.id,
                    "type": notification_type,
                    "payload": public_payload,
                    "created_at": utcnow(),
                }
                for uid in user_ids
            ]
        )
        .on_conflict_do_nothing(index_elements=["event_id", "user_id"])
    )


HANDLERS: list[Callable[[Session, OutboxEvent], None]] = [_notify]


def process_batch(limit: int = 100) -> int:
    with session_factory()() as session, session.begin():
        events = session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.processed_at.is_(None))
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        for event in events:
            try:
                with session.begin_nested():
                    for handler in HANDLERS:
                        handler(session, event)
                event.processed_at = utcnow()
            except Exception as exc:  # one bad event must not block the queue
                event.attempts += 1
                event.last_error = type(exc).__name__
                if event.attempts >= MAX_ATTEMPTS:
                    event.processed_at = utcnow()
                log.warning("outbox_handler_failed", event_type=event.type, attempts=event.attempts)
        return len(events)


def drain() -> int:
    """Process everything pending (tests and demo endpoints call this synchronously)."""
    total = 0
    while (n := process_batch()) > 0:
        total += n
    return total


async def run_worker(stop: asyncio.Event) -> None:
    poll = get_settings().worker_poll_seconds
    while not stop.is_set():
        processed = 0
        try:
            processed = await asyncio.to_thread(process_batch)
        except Exception:
            log.exception("outbox_worker_error")
        if processed == 0:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=poll)
