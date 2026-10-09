"""Two-phase settlement (MC-SET-01..06; invariants G4, G5, G6, G8, G9).

`settle` drives an APPROVED run to PREPARED (one hold per payer) and then to COMMITTED
(one journal entry). Each step is one database transaction, bracketed by a settlement job
that is written before the step starts and updated when it ends. Calling Settle again
after a crash therefore resumes from the last completed step, and calling it on a
committed run changes nothing (MC-SET-05).

Prepare problems that concern one member (funding, sanctions, member state) exclude that
member and recompute. A changed input or an expired FX lock aborts the run. Any error in a
step rolls that step back and aborts the run with every hold released.
"""

from collections import defaultdict
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.db import transaction
from app.core.enums import (
    NETTABLE_MEMBER_STATES,
    TERMINAL_RUN_STATES,
    CaseType,
    ExclusionReason,
    HoldStatus,
    InvoiceOutcomeKind,
    InvoiceStatus,
    JobStatus,
    JournalKind,
    KillSwitchScope,
    LedgerAccountType,
    PartyType,
    RunStatus,
    SettlementStep,
    TransferStatus,
)
from app.core.errors import AppError, Conflict, InvalidState
from app.core.hashing import sha256_hex
from app.core.ids import new_id, utcnow
from app.core.security import Principal
from app.events.outbox import emit
from app.modules.audit import service as audit
from app.modules.fx import service as fx
from app.modules.invoices.models import Invoice
from app.modules.invoices.state import transition
from app.modules.ledger import service as ledger
from app.modules.ledger.postings import (
    build_commit_postings,
    hold_postings,
    plan_holds,
    release_postings,
)
from app.modules.members.models import KillSwitch, Member
from app.modules.risk.models import Case
from app.modules.runs import reads, repository
from app.modules.runs import service as runs
from app.modules.runs.models import Cancellation, NettingRun, PlannedTransfer, RunComputation
from app.modules.runs.schemas import RunView
from app.modules.settlement import plan as stored
from app.modules.settlement.models import Hold, InvoiceOutcome, SettlementJob
from app.modules.statements import content as statement_content
from app.modules.statements.models import Approval, Statement
from app.modules.windows.models import RunInvoice

log = structlog.get_logger()
SWITCH_LOCK = 731001  # pg_advisory_xact_lock key shared with window close and switch writes

# When several members fail prepare at once, the recompute trigger names the first of these.
_TRIGGER_ORDER = (
    ExclusionReason.FUNDING_FAILED,
    ExclusionReason.SANCTIONS_HIT,
    ExclusionReason.MEMBER_NOT_ACTIVE,
)


class SettlementInvariantError(RuntimeError):
    """A money invariant failed inside a step; the step rolls back and the run aborts."""


def job_key(run_id: UUID, attempt: int, member_id: UUID | None, step: SettlementStep) -> str:
    """MC-SET-05: sha256 over run, computation attempt, member and step."""
    return sha256_hex(f"{run_id}:{attempt}:{member_id or '-'}:{step}")


# --- orchestration --------------------------------------------------------------------


def settle(session: Session, actor: Principal, run_id: UUID, reason: str) -> RunView:
    """Prepare and commit, resuming from the last completed step."""
    with transaction(session):
        run = runs.get_admin(session, run_id)
        if run.status not in {RunStatus.APPROVED, RunStatus.PREPARED, RunStatus.COMMITTED}:
            raise InvalidState(
                "Only an approved run can be settled.", details={"status": run.status}
            )
        attempt = run.current_attempt
    for step in (SettlementStep.PREPARE, SettlementStep.COMMIT):
        with transaction(session):
            run = runs.get_admin(session, run_id)
            status, current_attempt = run.status, run.current_attempt
        if current_attempt != attempt:
            break  # prepare excluded a member and recomputed: new statements need approval
        if step == SettlementStep.PREPARE and status != RunStatus.APPROVED:
            continue
        if step == SettlementStep.COMMIT and status != RunStatus.PREPARED:
            break
        _run_step(session, actor, run_id, attempt, step, reason)
    with transaction(session):
        return reads.run_view(session, runs.get_admin(session, run_id), None)


def _run_step(
    session: Session,
    actor: Principal,
    run_id: UUID,
    attempt: int,
    step: SettlementStep,
    reason: str,
) -> None:
    with transaction(session):
        job_id = _start_job(session, run_id, attempt, None, step).id
    work = _prepare if step == SettlementStep.PREPARE else _commit
    try:
        with transaction(session):
            result = work(session, actor, run_id, attempt, reason)
            _finish_job(session, job_id, JobStatus.DONE, result=result)
    except AppError as exc:
        # Refused before any change (kill switch, wrong state, missing approval).
        with transaction(session):
            _finish_job(session, job_id, JobStatus.FAILED, error=exc.code)
        raise
    except Exception as exc:
        # G9: the step rolled back; abort the run and release every hold.
        log.exception("settlement_step_failed", step=step, error_type=type(exc).__name__)
        with transaction(session):
            _finish_job(session, job_id, JobStatus.FAILED, error=type(exc).__name__)
            run = runs.get_admin(session, run_id, lock=True)
            if run.status not in TERMINAL_RUN_STATES:
                abort_run(session, run, None, f"{step}_ERROR")


def _start_job(
    session: Session, run_id: UUID, attempt: int, member_id: UUID | None, step: SettlementStep
) -> SettlementJob:
    key = job_key(run_id, attempt, member_id, step)
    session.execute(
        pg_insert(SettlementJob)
        .values(
            id=new_id(),
            run_id=run_id,
            member_id=member_id,
            step=step,
            idempotency_key=key,
            status=JobStatus.STARTED,
            attempts=0,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
    job = session.scalars(
        select(SettlementJob).where(SettlementJob.idempotency_key == key).with_for_update()
    ).one()
    job.status = JobStatus.STARTED
    job.attempts += 1
    job.last_error = None
    job.updated_at = utcnow()
    session.flush()
    return job


def _finish_job(
    session: Session,
    job_id: UUID,
    status: JobStatus,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    job = session.get(SettlementJob, job_id, with_for_update=True)
    assert job is not None
    job.status = status
    job.result = result
    job.last_error = error
    job.updated_at = utcnow()
    session.flush()


# --- prepare --------------------------------------------------------------------------


def _prepare(
    session: Session, actor: Principal, run_id: UUID, attempt: int, reason: str
) -> dict[str, Any]:
    session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": SWITCH_LOCK})
    run = runs.get_admin(session, run_id, lock=True)
    _expect(run, RunStatus.APPROVED, attempt)
    computation = repository.latest(session, run)
    assert computation is not None
    statements = _statements(session, computation)
    participants = sorted({s.member_id for s in statements}, key=str)
    _refuse_when_switched_off(session, participants)

    # G5: the frozen input is unchanged and every current statement is approved.
    if runs.stored_input_hash(session, run) != run.input_hash or _terms_changed(session, run):
        abort_run(session, run, actor, "INPUT_CHANGED")
        return {"outcome": "ABORTED", "reason": "INPUT_CHANGED"}
    _require_approvals(session, statements)
    if fx.expired(fx.current_locks(session, run.id, computation.created_at)):
        abort_run(session, run, actor, "FX_LOCK_EXPIRED")
        return {"outcome": "ABORTED", "reason": "FX_LOCK_EXPIRED"}

    plan = stored.load(session, computation)
    holds = plan_holds(plan, plan.fees)
    members = {m.id: m for m in session.scalars(select(Member).where(Member.id.in_(participants)))}
    removed: dict[UUID, ExclusionReason] = {}
    detail: dict[UUID, str] = {}
    for m in participants:
        if members[m].state not in NETTABLE_MEMBER_STATES:
            removed[m] = ExclusionReason.MEMBER_NOT_ACTIVE
    for m in sorted(runs.screen(session, run, set(participants), stage="PREPARE"), key=str):
        removed.setdefault(m, ExclusionReason.SANCTIONS_HIT)  # G8
    for m in participants:
        h = holds.get(m)
        if m in removed or h is None or h.hold_minor == 0:
            continue
        available = ledger.lock_balance(session, m, h.currency)
        if members[m].funding_blocked or available < h.hold_minor:
            removed[m] = ExclusionReason.FUNDING_FAILED
            detail[m] = "FUNDING_BLOCKED" if members[m].funding_blocked else "INSUFFICIENT_FUNDS"
    if removed:
        _exclude_and_recompute(session, run, actor, removed, detail)
        return {
            "outcome": "RECOMPUTED",
            "excluded": {
                str(m): r.value for m, r in sorted(removed.items(), key=lambda i: str(i[0]))
            },
        }

    for m in participants:
        h = holds.get(m)
        if h is None or h.hold_minor == 0:
            continue
        entry = ledger.post(
            session,
            kind=JournalKind.HOLD,
            lines=hold_postings(h),
            idempotency_key=f"hold:{run.id}:{attempt}:{m}",
            run_id=run.id,
        )
        hold = Hold(
            run_id=run.id,
            member_id=m,
            currency=h.currency,
            amount_minor=h.hold_minor,
            status=HoldStatus.ACTIVE,
            journal_entry_id=entry.id,
        )
        session.add(hold)
        session.flush()
        member_job = _start_job(session, run.id, attempt, m, SettlementStep.PREPARE)
        member_job.status = JobStatus.DONE
        member_job.result = {
            "hold_id": str(hold.id),
            "currency": h.currency,
            "amount_minor": h.hold_minor,
        }
        audit.record(
            session,
            actor=actor,
            action="settlement.hold_placed",
            subject_type="MEMBER",
            subject_id=m,
            run_id=run.id,
            after={"currency": h.currency, "amount_minor": h.hold_minor},
            reason_code=reason,
        )

    # MC-SET-01: the holds, as derived from postings, equal the total payable plus fees.
    held: dict[str, int] = defaultdict(int)
    for (_, currency), amount in ledger.run_account_balances(
        session, run.id, LedgerAccountType.MEMBER_HOLD
    ).items():
        held[currency] += amount
    payable: dict[str, int] = defaultdict(int)
    for p in plan.positions:
        if p.party_type == PartyType.MEMBER and p.member_id is not None:
            fee = plan.fees.get(p.member_id, 0)
            fee_from_receipt = min(fee, max(p.amount_minor, 0))
            payable[p.currency] += max(-p.amount_minor, 0) + fee - fee_from_receipt
    if {c: v for c, v in held.items() if v} != {c: v for c, v in payable.items() if v}:
        raise SettlementInvariantError(f"holds {dict(held)} don't match payables {dict(payable)}")
    runs.change(session, run, RunStatus.PREPARED, actor, reason)
    session.flush()
    return {"outcome": "PREPARED", "held_minor": dict(sorted(held.items()))}


def _exclude_and_recompute(
    session: Session,
    run: NettingRun,
    actor: Principal,
    removed: dict[UUID, ExclusionReason],
    detail: dict[UUID, str],
) -> None:
    for m, why in sorted(removed.items(), key=lambda i: str(i[0])):
        audit.record(
            session,
            actor=actor,
            action="settlement.member_excluded",
            subject_type="MEMBER",
            subject_id=m,
            run_id=run.id,
            reason_code=why,
            details={"detail": detail[m]} if m in detail else None,
        )
        if why == ExclusionReason.FUNDING_FAILED:
            session.add(
                Case(
                    type=CaseType.FUNDING,
                    subject_type="MEMBER",
                    subject_id=m,
                    run_id=run.id,
                    notes=f"{detail[m]} at prepare; member excluded and run recomputed.",
                )
            )
            emit(
                session, "run.funding_failed", run.id, {"run_id": str(run.id), "member_id": str(m)}
            )
    session.flush()
    trigger = next(r for r in _TRIGGER_ORDER if r in removed.values())
    runs.recompute(session, run, removed, trigger)


# --- commit ---------------------------------------------------------------------------


def _commit(
    session: Session, actor: Principal, run_id: UUID, attempt: int, reason: str
) -> dict[str, Any]:
    session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": SWITCH_LOCK})
    run = runs.get_admin(session, run_id, lock=True)
    _expect(run, RunStatus.PREPARED, attempt)
    computation = repository.latest(session, run)
    assert computation is not None
    statements = _statements(session, computation)
    _refuse_when_switched_off(session, sorted({s.member_id for s in statements}, key=str))
    if fx.expired(fx.current_locks(session, run.id, computation.created_at)):
        abort_run(session, run, actor, "FX_LOCK_EXPIRED")
        return {"outcome": "ABORTED", "reason": "FX_LOCK_EXPIRED"}

    plan = stored.load(session, computation)
    lines = build_commit_postings(plan, plan.fees)
    entry = (
        ledger.post(
            session,
            kind=JournalKind.COMMIT,
            lines=lines,
            idempotency_key=f"commit:{run.id}:{attempt}",
            run_id=run.id,
        )
        if lines
        else None
    )
    # MC-SET-02: the run's clearing and hold accounts are zero before the transaction commits.
    open_accounts = {
        (kind, currency): amount
        for kind in (LedgerAccountType.CLEARING, LedgerAccountType.MEMBER_HOLD)
        for (_, currency), amount in ledger.run_account_balances(session, run.id, kind).items()
        if amount
    }
    if open_accounts:
        raise SettlementInvariantError(f"run accounts not cleared: {open_accounts}")

    for hold in session.scalars(
        select(Hold)
        .where(Hold.run_id == run.id, Hold.status == HoldStatus.ACTIVE)
        .with_for_update()
    ):
        hold.status = HoldStatus.CONSUMED
        hold.release_entry_id = entry.id if entry else None  # the entry that closed the hold
        hold.updated_at = utcnow()
    for transfer in session.scalars(
        select(PlannedTransfer).where(PlannedTransfer.computation_id == computation.id)
    ):
        transfer.status = TransferStatus.SETTLED
    outcomes = _write_outcomes(session, run, computation, statements)
    runs.change(session, run, RunStatus.COMMITTED, actor, reason)
    emit(
        session,
        "run.committed",
        run.id,
        {"run_id": str(run.id), "member_ids": sorted(str(s.member_id) for s in statements)},
    )
    session.flush()
    return {
        "outcome": "COMMITTED",
        "journal_entry_id": str(entry.id) if entry else None,
        "invoice_outcomes": outcomes,
    }


def _write_outcomes(
    session: Session, run: NettingRun, computation: RunComputation, statements: list[Statement]
) -> int:
    """MC-SET-06 and G6: every locked invoice ends with exactly one outcome."""
    cancelled = {
        invoice_id: int(total)
        for invoice_id, total in session.execute(
            select(Cancellation.invoice_id, func.sum(Cancellation.amount_minor))
            .where(Cancellation.computation_id == computation.id)
            .group_by(Cancellation.invoice_id)
        ).tuples()
    }
    frozen = {
        r.invoice_id: r
        for r in session.scalars(select(RunInvoice).where(RunInvoice.run_id == run.id))
    }
    locked = list(
        session.scalars(
            select(Invoice)
            .where(Invoice.id.in_(list(frozen)), Invoice.status == InvoiceStatus.LOCKED_IN_RUN)
            .order_by(Invoice.id)
            .with_for_update()
        )
    )
    expected = {i for s in statements for i in statement_content.invoice_ids(s.content)}
    if {i.id for i in locked} != expected:
        raise SettlementInvariantError("locked invoices differ from the approved computation")
    for invoice in locked:
        outstanding = frozen[invoice.id].outstanding_minor
        cancelled_minor = cancelled.get(invoice.id, 0)
        residual = outstanding - cancelled_minor
        kind = (
            InvoiceOutcomeKind.SETTLED_BY_NETTING
            if residual == 0
            else InvoiceOutcomeKind.SETTLED_BY_TRANSFER
        )
        session.add(
            InvoiceOutcome(
                invoice_id=invoice.id,
                run_id=run.id,
                outcome=kind,
                outstanding_minor=outstanding,
                cancelled_minor=cancelled_minor,
                residual_minor=residual,
            )
        )
        transition(
            session,
            invoice,
            InvoiceStatus(kind.value),
            actor=None,
            run_id=run.id,
            reason_code="RUN_COMMITTED",
        )
    session.flush()
    return len(locked)


# --- abort ----------------------------------------------------------------------------


def abort(session: Session, actor: Principal, run_id: UUID, reason: str) -> RunView:
    """Staff abort (MC-SET-04). Called inside the idempotency transaction."""
    run = runs.get_admin(session, run_id, lock=True)
    if run.status == RunStatus.ABORTED:
        return reads.run_view(session, run, None)
    if run.status in TERMINAL_RUN_STATES:
        raise InvalidState("This run has already finished.", details={"status": run.status})
    job = _start_job(session, run.id, run.current_attempt, None, SettlementStep.ABORT)
    abort_run(session, run, actor, reason)
    job.status = JobStatus.DONE
    job.result = {"outcome": "ABORTED", "reason": reason}
    session.flush()
    return reads.run_view(session, run, None)


def abort_run(session: Session, run: NettingRun, actor: Principal | None, reason: str) -> None:
    """G9: release every active hold, cancel planned transfers, return invoices, ABORTED."""
    for hold in session.scalars(
        select(Hold)
        .where(Hold.run_id == run.id, Hold.status == HoldStatus.ACTIVE)
        .order_by(Hold.member_id, Hold.currency)
        .with_for_update()
    ):
        entry = ledger.post(
            session,
            kind=JournalKind.RELEASE,
            lines=release_postings(hold.member_id, hold.currency, hold.amount_minor),
            idempotency_key=f"release:{hold.id}",
            run_id=run.id,
        )
        hold.status = HoldStatus.RELEASED
        hold.release_entry_id = entry.id
        hold.updated_at = utcnow()
        audit.record(
            session,
            actor=actor,
            action="settlement.hold_released",
            subject_type="MEMBER",
            subject_id=hold.member_id,
            run_id=run.id,
            after={"currency": hold.currency, "amount_minor": hold.amount_minor},
            reason_code=reason,
        )
    computation = repository.latest(session, run)
    if computation is not None:
        for transfer in session.scalars(
            select(PlannedTransfer).where(
                PlannedTransfer.computation_id == computation.id,
                PlannedTransfer.status == TransferStatus.PLANNED,
            )
        ):
            transfer.status = TransferStatus.CANCELLED
    session.flush()
    runs.finish_without_settlement(session, run, RunStatus.ABORTED, reason, actor)
    session.flush()


# --- checks ---------------------------------------------------------------------------


def _expect(run: NettingRun, status: RunStatus, attempt: int) -> None:
    if run.status != status or run.current_attempt != attempt:
        raise InvalidState(
            f"The run is {run.status.lower().replace('_', ' ')}; it can't be settled now.",
            details={"status": run.status, "attempt": run.current_attempt},
        )


def _statements(session: Session, computation: RunComputation) -> list[Statement]:
    return list(
        session.scalars(
            select(Statement)
            .where(Statement.computation_id == computation.id)
            .order_by(Statement.member_id)
        )
    )


def _refuse_when_switched_off(session: Session, participants: list[UUID]) -> None:
    """MC-RSK-03: commit (and prepare before it) is refused while a relevant switch is on."""
    switches = list(session.scalars(select(KillSwitch).where(KillSwitch.enabled)))
    if any(k.scope == KillSwitchScope.GLOBAL for k in switches):
        raise Conflict("The global kill switch is enabled.", code="KILL_SWITCH_ON")
    paused = sorted(
        str(k.member_id)
        for k in switches
        if k.scope == KillSwitchScope.MEMBER and k.member_id in set(participants)
    )
    if paused:
        raise Conflict(
            "A member in this run is paused by its kill switch. Abort the run or lift the switch.",
            code="KILL_SWITCH_ON",
            details={"member_ids": paused},
        )


def _require_approvals(session: Session, statements: list[Statement]) -> None:
    for s in statements:
        approvals = session.scalar(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.statement_id == s.id,
                Approval.decision == "APPROVED",
                Approval.content_hash == s.content_hash,
            )
        )
        if (approvals or 0) < s.required_approvers:
            raise InvalidState("Every current statement needs its approvals before settlement.")


def _terms_changed(session: Session, run: NettingRun) -> bool:
    rows = session.execute(
        select(RunInvoice, Invoice)
        .join(Invoice, Invoice.id == RunInvoice.invoice_id)
        .where(RunInvoice.run_id == run.id, Invoice.status == InvoiceStatus.LOCKED_IN_RUN)
    ).tuples()
    return any(
        i.current_version != r.version
        or i.outstanding_minor != r.outstanding_minor
        or i.currency != r.currency
        or i.payer_member_id != r.payer_member_id
        or i.issuer_member_id != r.receiver_member_id
        for r, i in rows
    )
