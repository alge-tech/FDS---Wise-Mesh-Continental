"""In-app notifications (MC-UX-01). The outbox worker creates them; users read their own."""

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import NotFound
from app.core.idempotency import Idempotency, idempotency
from app.core.ids import utcnow
from app.core.schemas import ApiModel
from app.core.security import Principal, current_principal
from app.modules.notifications.models import Notification

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


class NotificationView(ApiModel):
    id: UUID
    type: str
    payload: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class NotificationList(ApiModel):
    items: list[NotificationView]
    unread_count: int


def _list(session: Session, user_id: UUID, limit: int) -> NotificationList:
    rows = session.scalars(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
    )
    unread = session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    return NotificationList(
        items=[NotificationView.model_validate(n) for n in rows], unread_count=int(unread or 0)
    )


@router.get("", response_model=NotificationList)
def notifications(
    limit: int = Query(default=20, ge=1, le=100),
    actor: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> NotificationList:
    return _list(session, actor.user_id, limit)


@router.post("/{notification_id}/read", response_model=NotificationList)
def mark_read(
    notification_id: UUID,
    actor: Principal = Depends(current_principal),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> NotificationList:
    def work(s: Session) -> NotificationList:
        row = s.scalar(
            select(Notification)
            .where(Notification.id == notification_id, Notification.user_id == actor.user_id)
            .with_for_update()
        )
        if row is None:
            raise NotFound()
        row.read_at = row.read_at or utcnow()
        s.flush()
        return _list(s, actor.user_id, 20)

    return cast(NotificationList, idem.run(session, work))
