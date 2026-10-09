"""Wise staff reads: risk cases and the audit log (MC-OPS-01)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.enums import Role
from app.core.schemas import ApiModel, Page
from app.core.security import Principal, require_roles
from app.modules.audit.models import AuditEvent
from app.modules.members.models import Member
from app.modules.risk.models import Case

router = APIRouter(prefix="/v1/admin", tags=["admin"])


class CaseView(ApiModel):
    id: UUID
    type: str
    subject_type: str
    subject_id: UUID
    subject_name: str | None
    run_id: UUID | None
    status: str
    notes: str | None
    created_at: datetime


class AuditView(ApiModel):
    id: UUID
    created_at: datetime
    actor_id: UUID | None
    actor_role: str | None
    action: str
    subject_type: str
    subject_id: UUID
    run_id: UUID | None
    reason_code: str | None
    before_hash: str | None
    after_hash: str | None
    details: dict[str, Any]
    correlation_id: str | None


@router.get("/cases", response_model=Page[CaseView])
def cases(
    status: str | None = None,
    actor: Principal = Depends(require_roles(Role.WISE_COMPLIANCE)),
    session: Session = Depends(get_session),
) -> Page[CaseView]:
    names = dict(session.execute(select(Member.id, Member.display_name)).tuples().all())
    query = select(Case).order_by(Case.created_at.desc(), Case.id.desc())
    if status:
        query = query.where(Case.status == status)
    return Page(
        items=[
            CaseView(
                id=c.id,
                type=c.type,
                subject_type=c.subject_type,
                subject_id=c.subject_id,
                subject_name=names.get(c.subject_id) if c.subject_type == "MEMBER" else None,
                run_id=c.run_id,
                status=c.status,
                notes=c.notes,
                created_at=c.created_at,
            )
            for c in session.scalars(query)
        ]
    )


@router.get("/audit-events", response_model=Page[AuditView])
def audit_events(
    run_id: UUID | None = None,
    subject_type: str | None = None,
    subject_id: UUID | None = None,
    action: str | None = Query(default=None, description="Exact action or a prefix ending in '.'"),
    cursor: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    actor: Principal = Depends(require_roles(Role.WISE_OPS, Role.WISE_COMPLIANCE)),
    session: Session = Depends(get_session),
) -> Page[AuditView]:
    """Newest first. IDs are UUIDv7, so the ID order is the order the events were written."""
    query = select(AuditEvent).order_by(AuditEvent.id.desc())
    if run_id is not None:
        query = query.where(AuditEvent.run_id == run_id)
    if subject_type:
        query = query.where(AuditEvent.subject_type == subject_type)
    if subject_id is not None:
        query = query.where(AuditEvent.subject_id == subject_id)
    if action:
        query = query.where(
            AuditEvent.action.startswith(action)
            if action.endswith(".")
            else AuditEvent.action == action
        )
    if cursor is not None:
        query = query.where(AuditEvent.id < cursor)
    rows = list(session.scalars(query.limit(limit + 1)))
    return Page(
        items=[AuditView.model_validate(e) for e in rows[:limit]],
        next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
    )
