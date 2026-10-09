from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ExclusionReason, RunStatus
from app.core.errors import Conflict, Forbidden, InvalidState, NotFound
from app.core.security import Principal
from app.events.outbox import emit
from app.modules.audit import service as audit
from app.modules.fx import service as fx
from app.modules.runs import reads, repository
from app.modules.runs import service as runs
from app.modules.runs.models import RunComputation
from app.modules.runs.schemas import ApprovalRequest, RunView
from app.modules.statements.models import Approval, Statement


def approve(
    session: Session, actor: Principal, statement_id: UUID, body: ApprovalRequest
) -> RunView:
    assert actor.member_id is not None
    statement = repository.statement_for_member(session, actor.member_id, statement_id)
    if statement is None:
        raise NotFound()
    computation = session.get(RunComputation, statement.computation_id)
    assert computation is not None
    run = runs.get_admin(session, computation.run_id, lock=True)
    latest = repository.latest(session, run)
    current = (
        session.scalar(
            select(Statement).where(
                Statement.computation_id == latest.id, Statement.member_id == actor.member_id
            )
        )
        if latest
        else None
    )
    if computation.attempt != run.current_attempt or body.content_hash != statement.content_hash:
        raise Conflict(
            "The statement has changed. Review the current statement.",
            code="STATEMENT_CHANGED",
            details={"current_statement_id": str(current.id) if current else None},
        )
    if run.status != RunStatus.AWAITING_APPROVAL:
        raise InvalidState("This run is not awaiting approval.")
    if not reads.permitted(actor, statement):
        raise Forbidden("Above the threshold, an approver or member admin must approve.")
    existing = session.scalar(
        select(Approval).where(
            Approval.statement_id == statement.id, Approval.approver_id == actor.user_id
        )
    )
    if existing:
        raise Conflict("You have already answered this statement.", code="ALREADY_APPROVED")
    already_approved = list(
        session.scalars(
            select(Approval).where(
                Approval.statement_id == statement.id,
                Approval.content_hash == statement.content_hash,
                Approval.decision == "APPROVED",
            )
        )
    )
    if len(already_approved) >= statement.required_approvers:
        raise InvalidState("This statement already has all required approvals.")
    session.add(
        Approval(
            statement_id=statement.id,
            approver_id=actor.user_id,
            decision="APPROVED" if body.decision == "APPROVE" else "REJECTED",
            content_hash=body.content_hash,
        )
    )
    audit.record(
        session,
        actor=actor,
        action="statement.approval",
        subject_type="STATEMENT",
        subject_id=statement.id,
        run_id=run.id,
        reason_code=body.reason_code or body.decision,
        after={"decision": body.decision, "content_hash": body.content_hash},
    )
    emit(
        session,
        "run.approval_received",
        run.id,
        {"member_id": str(actor.member_id), "run_id": str(run.id)},
    )
    session.flush()
    if body.decision == "REJECT":
        runs.recompute(
            session,
            run,
            {actor.member_id: ExclusionReason.REJECTED_STATEMENT},
            "REJECTED_STATEMENT",
        )
    else:
        maybe_approved(session, run.id)
    return reads.run_view(session, run, actor.member_id)


def maybe_approved(session: Session, run_id: UUID) -> None:
    run = runs.get_admin(session, run_id)
    current = repository.latest(session, run)
    if current is None or run.status != RunStatus.AWAITING_APPROVAL:
        return
    statements = list(
        session.scalars(select(Statement).where(Statement.computation_id == current.id))
    )
    if statements and all(
        len(
            list(
                session.scalars(
                    select(Approval).where(
                        Approval.statement_id == s.id,
                        Approval.content_hash == s.content_hash,
                        Approval.decision == "APPROVED",
                    )
                )
            )
        )
        >= s.required_approvers
        for s in statements
    ):
        runs.change(session, run, RunStatus.APPROVED, None, "ALL_APPROVED")
        fx.lock_rates(session, run.id, current.id)
