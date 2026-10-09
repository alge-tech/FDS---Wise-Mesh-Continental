"""Demo controls for the settlement path: funding failures and expired approvals."""

from uuid import UUID

from pydantic import field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import ExclusionReason, RunStatus
from app.core.errors import InvalidState, NotFound
from app.core.schemas import ApiModel, StrictModel
from app.core.security import Principal
from app.modules.audit import service as audit
from app.modules.members.models import Member
from app.modules.runs import reads, repository
from app.modules.runs import service as runs
from app.modules.runs.schemas import RunView
from app.modules.statements.models import Approval, Statement


def _uuid(value: str) -> str:
    UUID(value)
    return value


class FundingFailure(StrictModel):
    member_id: str
    unable_to_fund: bool = True

    _valid = field_validator("member_id")(lambda cls, v: _uuid(v))


class FundingState(ApiModel):
    member_id: UUID
    name: str
    funding_blocked: bool


class ExpireApprovals(StrictModel):
    run_id: str

    _valid = field_validator("run_id")(lambda cls, v: _uuid(v))


def funding_failure(session: Session, body: FundingFailure, actor: Principal) -> FundingState:
    """MC-SET-03: the member can't fund; the next prepare excludes it and recomputes."""
    member = session.get(Member, UUID(body.member_id), with_for_update=True)
    if member is None:
        raise NotFound()
    before = member.funding_blocked
    member.funding_blocked = body.unable_to_fund
    audit.record(
        session,
        actor=actor,
        action="demo.funding_failure",
        subject_type="MEMBER",
        subject_id=member.id,
        before={"funding_blocked": before},
        after={"funding_blocked": member.funding_blocked},
        reason_code="DEMO_FUNDING_FAILURE",
    )
    session.flush()
    return FundingState(
        member_id=member.id, name=member.display_name, funding_blocked=member.funding_blocked
    )


def expire_approvals(session: Session, body: ExpireApprovals, actor: Principal) -> RunView:
    """MC-APR-05: members without all their approvals are removed and the run recomputes."""
    run = runs.get_admin(session, UUID(body.run_id), lock=True)
    if run.status != RunStatus.AWAITING_APPROVAL:
        raise InvalidState("Only a run awaiting approval has approvals to expire.")
    computation = repository.latest(session, run)
    assert computation is not None
    pending = set()
    for statement in session.scalars(
        select(Statement).where(Statement.computation_id == computation.id)
    ):
        approved = session.scalar(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.statement_id == statement.id,
                Approval.decision == "APPROVED",
                Approval.content_hash == statement.content_hash,
            )
        )
        if (approved or 0) < statement.required_approvers:
            pending.add(statement.member_id)
    if not pending:
        raise InvalidState("Every member has already approved this run.")
    audit.record(
        session,
        actor=actor,
        action="demo.expire_approvals",
        subject_type="RUN",
        subject_id=run.id,
        run_id=run.id,
        reason_code="APPROVAL_EXPIRED",
        details={"members_removed": len(pending)},
    )
    runs.recompute(
        session, run, dict.fromkeys(pending, ExclusionReason.APPROVAL_EXPIRED), "APPROVAL_EXPIRED"
    )
    session.flush()
    return reads.run_view(session, run, None)
