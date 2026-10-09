"""Audit writes (MC-OPS-01). Always called inside the caller's transaction."""

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.hashing import hash_canonical
from app.core.logging import correlation_id_var
from app.core.security import Principal
from app.modules.audit.models import AuditEvent


def record(
    session: Session,
    *,
    actor: Principal | None,
    action: str,
    subject_type: str,
    subject_id: UUID,
    run_id: UUID | None = None,
    before: Any = None,
    after: Any = None,
    reason_code: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_id=actor.user_id if actor else None,
        actor_role=actor.role if actor else "SYSTEM",
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        run_id=run_id,
        before_hash=hash_canonical(before) if before is not None else None,
        after_hash=hash_canonical(after) if after is not None else None,
        reason_code=reason_code,
        details=details or {},
        correlation_id=correlation_id_var.get(),
    )
    session.add(event)
    return event
