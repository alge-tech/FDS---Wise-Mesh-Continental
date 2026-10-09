from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import MEMBER_ROLES, Role
from app.core.errors import NotFound
from app.core.security import Principal
from app.modules.audit.models import AuditEvent
from app.modules.invoices.repository import involves
from app.modules.members.models import KillSwitch, Member
from app.modules.runs import repository
from app.modules.runs.models import NetPosition, NettingRun, RunComputation
from app.modules.runs.schemas import (
    AdminOverview,
    KillView,
    MemberRow,
    RunView,
    StatementView,
    WindowView,
)
from app.modules.settlement import reads as settlement
from app.modules.statements import content as statement_content
from app.modules.statements.models import Approval, Statement
from app.modules.windows.eligibility import eligible, public_reason
from app.modules.windows.models import Window


def current_window(session: Session, actor: Principal) -> WindowView:
    window = session.scalar(select(Window).where(Window.status == "OPEN"))
    if window is None:
        raise NotFound()
    included, excluded = eligible(session, window)

    def own(i_id: UUID) -> bool:
        if actor.is_staff:
            return True
        assert actor.member_id is not None
        from app.modules.invoices.models import Invoice

        return (
            session.scalar(select(Invoice.id).where(Invoice.id == i_id, involves(actor.member_id)))
            is not None
        )

    included = [i for i in included if own(i.id)]
    excluded = [e for e in excluded if own(e.invoice.id)]
    return WindowView(
        id=window.id,
        opened_at=window.opened_at,
        horizon_days=window.horizon_days,
        eligible_count=len(included),
        excluded_count=len(excluded),
        eligible_invoice_ids=[i.id for i in included],
        exclusions=[
            {
                "invoice_id": str(e.invoice.id),
                "reason": e.reason
                if actor.is_staff
                else public_reason(e.reason, e.member_id, actor.member_id),
            }
            for e in excluded
        ],
    )


def run_view(session: Session, run: NettingRun, member_id: UUID | None) -> RunView:
    computation = repository.latest(session, run)
    statement = (
        session.scalar(
            select(Statement).where(
                Statement.computation_id == computation.id, Statement.member_id == member_id
            )
        )
        if computation and member_id
        else None
    )
    events = list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.run_id == run.id, AuditEvent.subject_type == "RUN")
            .order_by(AuditEvent.created_at)
        )
    )
    return RunView(
        id=run.id,
        status=run.status,
        status_reason=run.status_reason,
        current_attempt=run.current_attempt,
        started_at=run.started_at,
        statement_id=statement.id if statement else None,
        content_hash=statement.content_hash if statement else None,
        own_positions=[
            {"currency": p.currency, "amount_minor": p.amount_minor}
            for p in session.scalars(
                select(NetPosition).where(
                    NetPosition.computation_id == computation.id, NetPosition.member_id == member_id
                )
            )
        ]
        if computation and member_id
        else [],
        approvals=[
            {"decision": a.decision, "method": a.method}
            for a in session.scalars(select(Approval).where(Approval.statement_id == statement.id))
        ]
        if statement
        else [],
        # Member timelines expose lifecycle only; no exclusion reason about other parties.
        timeline=[
            {
                "action": e.action,
                "created_at": e.created_at.isoformat(),
                **({"reason": e.reason_code} if member_id is None else {}),
            }
            for e in events
        ],
        computations=[
            {
                "id": str(c.id),
                "attempt": c.attempt,
                "metrics": c.metrics,
                "input_hash": c.input_hash,
                "result_hash": c.result_hash,
                "excluded_members": c.excluded_members,
                "trigger": c.trigger,
            }
            for c in session.scalars(
                select(RunComputation)
                .where(RunComputation.run_id == run.id)
                .order_by(RunComputation.attempt)
            )
        ]
        if member_id is None
        else [],
        finished_at=run.finished_at,
        settlement=settlement.member_settlement(session, run, member_id, statement)
        if member_id
        else None,
        settlement_detail=settlement.settlement_detail(session, run) if member_id is None else None,
    )


def permitted(actor: Principal, statement: Statement) -> bool:
    if actor.role not in MEMBER_ROLES or actor.member_id != statement.member_id:
        return False
    return actor.role != Role.FINANCE_USER or statement.required_approvers == 1


def statement_view(session: Session, actor: Principal, statement_id: UUID) -> StatementView:
    assert actor.member_id is not None
    statement = repository.statement_for_member(session, actor.member_id, statement_id)
    if statement is None:
        raise NotFound()
    computation = session.get(RunComputation, statement.computation_id)
    assert computation is not None
    run = session.get(NettingRun, computation.run_id)
    assert run is not None
    latest = repository.latest(session, run)
    current_statement = (
        session.scalar(
            select(Statement).where(
                Statement.computation_id == latest.id, Statement.member_id == actor.member_id
            )
        )
        if latest
        else None
    )
    approvals = list(
        session.scalars(
            select(Approval).where(
                Approval.statement_id == statement.id,
                Approval.content_hash == statement.content_hash,
                Approval.decision == "APPROVED",
            )
        )
    )
    current = computation.attempt == run.current_attempt
    content = statement.content
    return StatementView.model_validate(
        {
            **content,
            "statement_id": statement.id,
            "run_id": run.id,
            "attempt": computation.attempt,
            "member_id": statement.member_id,
            "instruction": {
                **content["instruction"],
                "reference": statement_content.reference(run.id, statement.member_id),
            },
            "approval": {
                "required_approvers": statement.required_approvers,
                "deadline": statement.expires_at,
                "approval_count": len(approvals),
                "can_approve": current
                and run.status == "AWAITING_APPROVAL"
                and permitted(actor, statement)
                and len(approvals) < statement.required_approvers
                and not any(a.approver_id == actor.user_id for a in approvals),
            },
            "can_withdraw": current
            and run.status in ("AWAITING_APPROVAL", "APPROVED")
            and actor.role in (Role.MEMBER_ADMIN, Role.FINANCE_USER),
            "content_hash": statement.content_hash,
            "run_status": run.status,
            "current": current,
            "current_statement_id": current_statement.id if current_statement else None,
            "issued_at": statement.issued_at,
        }
    )


def overview(session: Session) -> AdminOverview:
    return AdminOverview(
        members=[
            MemberRow(
                id=m.id, name=m.display_name, state=m.state, funding_blocked=m.funding_blocked
            )
            for m in session.scalars(select(Member).order_by(Member.display_name))
        ],
        runs=[
            run_view(session, r, None)
            for r in session.scalars(select(NettingRun).order_by(NettingRun.started_at.desc()))
        ],
        kill_switches=[
            KillView.model_validate(k)
            for k in session.scalars(select(KillSwitch).order_by(KillSwitch.scope))
        ],
    )
