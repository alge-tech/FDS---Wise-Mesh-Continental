from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.core.ids import utcnow
from app.core.security import Principal
from app.modules.audit import service as audit
from app.modules.members.models import KillSwitch, Member
from app.modules.runs import reads
from app.modules.runs.schemas import AdminOverview, KillRequest


def set_switch(session: Session, actor: Principal, body: KillRequest) -> AdminOverview:
    session.execute(text("SELECT pg_advisory_xact_lock(731001)"))
    member_id = UUID(body.member_id) if body.member_id else None
    if member_id and session.get(Member, member_id) is None:
        raise NotFound()
    switch = session.scalar(
        select(KillSwitch)
        .where(KillSwitch.scope == body.scope, KillSwitch.member_id == member_id)
        .with_for_update()
    )
    if switch is None:
        switch = KillSwitch(scope=body.scope, member_id=member_id)
        session.add(switch)
        session.flush()
    before = {"enabled": switch.enabled}
    switch.enabled = body.enabled
    switch.reason = body.reason
    switch.changed_by = actor.user_id
    switch.changed_at = utcnow()
    audit.record(
        session,
        actor=actor,
        action="kill_switch.changed",
        subject_type="KILL_SWITCH",
        subject_id=switch.id,
        before=before,
        after={
            "enabled": switch.enabled,
            "scope": switch.scope,
            "member_id": str(member_id) if member_id else None,
        },
        reason_code=body.reason,
    )
    session.flush()
    return reads.overview(session)
