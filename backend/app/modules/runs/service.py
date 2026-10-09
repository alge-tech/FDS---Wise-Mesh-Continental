"""Freeze, screen, persist computations, issue statements and bounded recomputation."""

from collections.abc import Iterable, Mapping
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import (
    TERMINAL_RUN_STATES,
    ExclusionReason,
    InvoiceStatus,
    LedgerAccountType,
    RiskDecisionKind,
    RunStatus,
)
from app.core.errors import Conflict, InvalidState, NotFound
from app.core.hashing import hash_canonical
from app.core.ids import utcnow
from app.core.money import convert_minor
from app.core.security import Principal
from app.events.outbox import emit
from app.modules.audit import service as audit
from app.modules.fx.models import Currency, FxRate, RateSnapshot
from app.modules.invoices.models import Invoice
from app.modules.invoices.state import transition
from app.modules.ledger.models import LedgerAccount, Posting
from app.modules.members.models import KillSwitch, LegalEntity, Member
from app.modules.netting.engine import run_netting
from app.modules.netting.fx_pass import lookup_rate
from app.modules.netting.types import CarryIn, Edge, EngineInput, EngineInvariantError
from app.modules.pricing.calc import MemberPricingInput, compute_fees
from app.modules.pricing.models import FeeCharge
from app.modules.risk.models import Case, RiskDecision, SanctionsEntry
from app.modules.risk.rules import RingInvoice, find_rings
from app.modules.runs import repository
from app.modules.runs.models import (
    Cancellation,
    FxLeg,
    NetPosition,
    NettingRun,
    PlannedTransfer,
    RunComputation,
    Withdrawal,
)
from app.modules.statements import content as statement_content
from app.modules.statements.builder import build
from app.modules.statements.models import Approval, Statement
from app.modules.windows.eligibility import eligible, public_reason
from app.modules.windows.models import InvoiceExclusion, RunInvoice, Window


def change(
    session: Session, run: NettingRun, status: RunStatus, actor: Principal | None, reason: str
) -> None:
    before = run.status
    run.status = status
    run.status_reason = reason
    if status in TERMINAL_RUN_STATES:
        run.finished_at = utcnow()
    audit.record(
        session,
        actor=actor,
        action=f"run.{status.lower()}",
        subject_type="RUN",
        subject_id=run.id,
        run_id=run.id,
        before={"status": before},
        after={"status": status},
        reason_code=reason,
    )


def exclude(
    session: Session,
    run: NettingRun,
    invoice: Invoice,
    reason: ExclusionReason,
    member_id: UUID | None,
    computation_id: UUID | None = None,
) -> None:
    session.add(
        InvoiceExclusion(
            window_id=run.window_id,
            run_id=run.id,
            computation_id=computation_id,
            invoice_id=invoice.id,
            excluded_member_id=member_id,
            public_reason=public_reason(reason, member_id, None),
            internal_reason=reason,
        )
    )


def release(session: Session, run: NettingRun, invoice: Invoice, reason: str) -> None:
    if invoice.status == InvoiceStatus.LOCKED_IN_RUN:
        transition(
            session, invoice, InvoiceStatus.RELEASED, actor=None, run_id=run.id, reason_code=reason
        )
        transition(
            session, invoice, InvoiceStatus.CONFIRMED, actor=None, run_id=run.id, reason_code=reason
        )


def frozen_hash(rows: Iterable[tuple[UUID, int, UUID | None, UUID | None, str, int]]) -> str:
    """Hash of the frozen set, in invoice ID order. Freeze stores it; prepare recomputes it."""
    return hash_canonical(
        [
            {
                "invoice_id": str(invoice_id),
                "version": version,
                "payer": str(payer),
                "receiver": str(receiver),
                "currency": currency,
                "outstanding_minor": outstanding,
            }
            for invoice_id, version, payer, receiver, currency, outstanding in sorted(
                rows, key=lambda r: r[0]
            )
        ]
    )


def stored_input_hash(session: Session, run: NettingRun) -> str:
    """Recompute the input hash from run_invoices, exactly as freeze computed it."""
    return frozen_hash(
        (
            r.invoice_id,
            r.version,
            r.payer_member_id,
            r.receiver_member_id,
            r.currency,
            r.outstanding_minor,
        )
        for r in session.scalars(select(RunInvoice).where(RunInvoice.run_id == run.id))
    )


def snapshot_rates(session: Session, run_id: UUID) -> dict[tuple[str, str], Decimal]:
    """The run's rate snapshot; a later snapshot row for a pair supersedes an earlier one."""
    return {
        (r.base, r.quote): r.rate
        for r in session.scalars(
            select(RateSnapshot)
            .where(RateSnapshot.run_id == run_id)
            .order_by(RateSnapshot.captured_at, RateSnapshot.id)
        )
    }


def carry_in(session: Session, run: NettingRun) -> tuple[CarryIn, ...]:
    """Dust parked in members' SUSPENSE accounts by earlier commits, paid out in this run.

    Only one active run may claim carried dust: if another run is still in flight, this one
    leaves the suspense balances alone, so the same dust can never be paid out twice.
    """
    others = session.scalar(
        select(NettingRun.id).where(
            NettingRun.id != run.id, NettingRun.status.not_in(list(TERMINAL_RUN_STATES))
        )
    )
    if others is not None:
        return ()
    rows = session.execute(
        select(LedgerAccount.member_id, LedgerAccount.currency, func.sum(Posting.amount_minor))
        .join(Posting, Posting.account_id == LedgerAccount.id)
        .where(
            LedgerAccount.type == LedgerAccountType.SUSPENSE,
            LedgerAccount.member_id.is_not(None),
        )
        .group_by(LedgerAccount.member_id, LedgerAccount.currency)
        .order_by(LedgerAccount.member_id, LedgerAccount.currency)
    ).all()
    return tuple(CarryIn(m, c, int(v)) for m, c, v in rows if m is not None and int(v) != 0)


def close(session: Session, actor: Principal, reason: str) -> NettingRun:
    # All switch writes use this same transaction lock: close and global switch are ordered.
    session.execute(text("SELECT pg_advisory_xact_lock(731001)"))
    if session.scalar(
        select(KillSwitch.id).where(KillSwitch.scope == "GLOBAL", KillSwitch.enabled)
    ):
        raise Conflict("The global kill switch is enabled.", code="KILL_SWITCH_ON")
    window = session.scalar(select(Window).where(Window.status == "OPEN").with_for_update())
    if window is None:
        raise InvalidState("There is no open window.")
    # Lock candidate terms before evaluating confirmations and copying them.
    list(
        session.scalars(
            select(Invoice)
            .where(
                Invoice.status.in_(["UNMATCHED", "PENDING_CONFIRMATION", "DISPUTED", "CONFIRMED"])
            )
            .order_by(Invoice.id)
            .with_for_update()
        )
    )
    included, excluded = eligible(session, window)
    if not included:
        raise InvalidState("The window has no eligible invoices.")
    window.status = "CLOSED"
    window.closed_at = utcnow()
    run = NettingRun(
        window_id=window.id,
        input_hash=frozen_hash(
            (
                i.id,
                i.current_version,
                i.payer_member_id,
                i.issuer_member_id,
                i.currency,
                i.outstanding_minor,
            )
            for i in included
        ),
    )
    session.add(run)
    session.flush()
    audit.record(
        session,
        actor=actor,
        action="run.frozen",
        subject_type="RUN",
        subject_id=run.id,
        run_id=run.id,
        reason_code=reason,
        after={"input_hash": run.input_hash},
    )
    for item in excluded:
        exclude(session, run, item.invoice, item.reason, item.member_id)
    for i in included:
        assert i.payer_member_id and i.issuer_member_id
        session.add(
            RunInvoice(
                run_id=run.id,
                invoice_id=i.id,
                version=i.current_version,
                payer_member_id=i.payer_member_id,
                receiver_member_id=i.issuer_member_id,
                currency=i.currency,
                outstanding_minor=i.outstanding_minor,
            )
        )
        transition(
            session, i, InvoiceStatus.LOCKED_IN_RUN, actor=actor, run_id=run.id, reason_code=reason
        )
    for rate in session.scalars(select(FxRate).order_by(FxRate.valid_from, FxRate.id)):
        session.add(
            RateSnapshot(
                run_id=run.id, base=rate.base, quote=rate.quote, rate=rate.rate, source=rate.source
            )
        )
    session.add(Window(rules_version=window.rules_version, horizon_days=window.horizon_days))
    session.flush()
    emit(session, "window.frozen", run.id, {"run_id": str(run.id)})
    blocked = screen(session, run)
    for i in included:
        hit = next((m for m in (i.payer_member_id, i.issuer_member_id) if m in blocked), None)
        if hit:
            exclude(session, run, i, ExclusionReason.SANCTIONS_HIT, hit)
            release(session, run, i, "SANCTIONS_HIT")
    hold_rings(session, run)
    change(session, run, RunStatus.SCREENED, None, "SCREENING_COMPLETE")
    compute(session, run, blocked, "WINDOW_CLOSE")
    return run


def screen(
    session: Session, run: NettingRun, parties: set[UUID] | None = None, stage: str = "FREEZE"
) -> set[UUID]:
    """Mock sanctions screening (MC-RSK-01, G8): at freeze for every party, again in prepare."""
    from app.modules.invoices.parsing import normalise_tax_id

    entries = list(session.scalars(select(SanctionsEntry)))
    if parties is None:
        parties = set(
            session.scalars(select(RunInvoice.payer_member_id).where(RunInvoice.run_id == run.id))
        )
        parties.update(
            session.scalars(
                select(RunInvoice.receiver_member_id).where(RunInvoice.run_id == run.id)
            )
        )
    blocked: set[UUID] = set()
    for m, e in session.execute(
        select(Member, LegalEntity)
        .join(LegalEntity, LegalEntity.id == Member.legal_entity_id)
        .where(Member.id.in_(parties))
    ):
        hit = any(
            (entry.tax_id and normalise_tax_id(entry.tax_id) == normalise_tax_id(e.tax_id))
            or (
                " ".join(entry.name.lower().split()) == " ".join(e.legal_name.lower().split())
                and entry.country == e.country
            )
            for entry in entries
        )
        session.add(
            RiskDecision(
                run_id=run.id,
                subject_type="MEMBER",
                subject_id=m.id,
                rule="MOCK_SANCTIONS",
                decision="EXCLUDE" if hit else "ALLOW",
                reasons={"hit": bool(hit), "stage": stage},
            )
        )
        audit.record(
            session,
            actor=None,
            action="risk.screened",
            subject_type="MEMBER",
            subject_id=m.id,
            run_id=run.id,
            reason_code="SANCTIONS_HIT" if hit else "SCREEN_CLEAR",
            details={"stage": stage},
        )
        if hit:
            blocked.add(m.id)
            session.add(
                Case(
                    type="SANCTIONS",
                    subject_type="MEMBER",
                    subject_id=m.id,
                    run_id=run.id,
                    notes=f"Mock sanctions list match at {stage.lower()}.",
                )
            )
    return blocked


def hold_rings(session: Session, run: NettingRun) -> int:
    """MC-RSK-02: hold every ring's invoices for review and open one RING case per ring."""
    settings = get_settings()
    since = utcnow() - timedelta(days=settings.ring_recent_days)
    recent = set(session.scalars(select(Member.id).where(Member.created_at >= since)))
    if not recent:
        return 0
    rows = session.execute(
        select(RunInvoice, Invoice)
        .join(Invoice, Invoice.id == RunInvoice.invoice_id)
        .where(RunInvoice.run_id == run.id, Invoice.status == InvoiceStatus.LOCKED_IN_RUN)
        .order_by(RunInvoice.invoice_id)
    ).all()
    invoices = {i.id: i for _, i in rows}
    units = {
        code: settings.ring_round_major * 10**exponent
        for code, exponent in session.execute(select(Currency.code, Currency.exponent)).tuples()
    }
    rings = find_rings(
        (
            RingInvoice(
                r.invoice_id,
                r.payer_member_id,
                r.receiver_member_id,
                r.currency,
                r.outstanding_minor,
            )
            for r, _ in rows
        ),
        recent,
        units,
    )
    for ring in rings:
        members = sorted({str(m) for r in ring for m in (r.payer, r.receiver)})
        reasons = {
            "members": members,
            "currency": ring[0].currency,
            "amount_minor": ring[0].amount_minor,
            "invoice_ids": [str(r.invoice_id) for r in ring],
        }
        for r in ring:
            invoice = invoices[r.invoice_id]
            session.add(
                RiskDecision(
                    run_id=run.id,
                    subject_type="INVOICE",
                    subject_id=invoice.id,
                    rule="RING",
                    decision=RiskDecisionKind.HOLD_FOR_REVIEW,
                    reasons=reasons,
                )
            )
            exclude(session, run, invoice, ExclusionReason.HOLD_FOR_REVIEW, None)
            release(session, run, invoice, "HOLD_FOR_REVIEW")
        session.add(
            Case(
                type="RING",
                subject_type="RUN",
                subject_id=run.id,
                run_id=run.id,
                notes=(
                    f"Ring of {len(ring)} invoices of {ring[0].currency} "
                    f"{ring[0].amount_minor} minor units between {len(members)} new members."
                ),
            )
        )
        audit.record(
            session,
            actor=None,
            action="risk.ring_held",
            subject_type="RUN",
            subject_id=run.id,
            run_id=run.id,
            reason_code="HOLD_FOR_REVIEW",
            details=reasons,
        )
    return len(rings)


def withdraw(
    session: Session, actor: Principal, run_id: UUID, invoice_ids: set[UUID], reason: str
) -> NettingRun:
    """MC-APR-03: take some of the caller's own invoices out of the run, then recompute.

    Like a rejection this is one exclusion event, so it counts towards the recompute cap.
    """
    assert actor.member_id is not None
    if repository.get_for_member(session, actor.member_id, run_id) is None:
        raise NotFound()
    run = get_admin(session, run_id, lock=True)
    if run.status not in (RunStatus.AWAITING_APPROVAL, RunStatus.APPROVED):
        raise InvalidState("Invoices can only be withdrawn while the run awaits approval.")
    current = repository.latest(session, run)
    assert current is not None
    statement = session.scalar(
        select(Statement).where(
            Statement.computation_id == current.id, Statement.member_id == actor.member_id
        )
    )
    own = statement_content.invoice_ids(statement.content) if statement else set()
    if not invoice_ids or not invoice_ids <= own:
        raise NotFound("Those invoices are not on your current statement.")
    for invoice in session.scalars(
        select(Invoice).where(Invoice.id.in_(invoice_ids)).order_by(Invoice.id).with_for_update()
    ):
        session.add(
            Withdrawal(
                run_id=run.id,
                member_id=actor.member_id,
                invoice_id=invoice.id,
                created_by=actor.user_id,
            )
        )
        exclude(session, run, invoice, ExclusionReason.WITHDRAWN, actor.member_id, current.id)
        release(session, run, invoice, "WITHDRAWN")
    audit.record(
        session,
        actor=actor,
        action="run.withdrawal",
        subject_type="RUN",
        subject_id=run.id,
        run_id=run.id,
        reason_code=reason,
        details={"invoice_ids": sorted(str(i) for i in invoice_ids)},
    )
    recompute(session, run, {}, "WITHDRAWN")
    return run


def compute(session: Session, run: NettingRun, excluded: set[UUID], trigger: str) -> None:
    settings = get_settings()
    previous = repository.latest(session, run)
    old_statements = (
        list(session.scalars(select(Statement).where(Statement.computation_id == previous.id)))
        if previous
        else []
    )
    members = {m.id: m for m in session.scalars(select(Member))}
    # Released invoices (excluded members, withdrawals, ring holds, failed components) stay
    # frozen for the input hash but are not netted again. Sessions don't autoflush.
    session.flush()
    frozen = list(
        session.scalars(
            select(RunInvoice)
            .join(Invoice, Invoice.id == RunInvoice.invoice_id)
            .where(RunInvoice.run_id == run.id, Invoice.status == InvoiceStatus.LOCKED_IN_RUN)
            .order_by(RunInvoice.invoice_id)
        )
    )
    rates = snapshot_rates(session, run.id)
    exponents = dict(session.execute(select(Currency.code, Currency.exponent)).tuples().all())
    inp = EngineInput(
        edges=tuple(
            Edge(
                i.invoice_id,
                i.payer_member_id,
                i.receiver_member_id,
                i.outstanding_minor,
                i.currency,
            )
            for i in frozen
        ),
        rates=rates,
        settlement_currency={m.id: m.settlement_currency for m in members.values()},
        payable_limit_minor={
            m.id: m.payable_limit_minor
            for m in members.values()
            if m.payable_limit_minor is not None
        },
        excluded_members=frozenset(excluded),
        time_budget_ms=settings.netting_time_budget_ms,
        algo_version=settings.algo_version,
        currency_exponents=exponents,
        dust_threshold_minor=settings.dust_threshold_minor,
        carry_in=carry_in(session, run),
    )
    try:
        result = run_netting(inp)
    except EngineInvariantError as exc:
        session.add(
            Case(
                type="ENGINE_ALERT",
                subject_type="RUN",
                subject_id=run.id,
                run_id=run.id,
                notes=str(exc),
            )
        )
        finish_without_settlement(session, run, RunStatus.ABORTED, "ENGINE_INVARIANT")
        return
    if result.component_errors:
        # MC-NET-01: the failed components' invoices are released below; the rest still net.
        session.add(
            Case(
                type="ENGINE_ALERT",
                subject_type="RUN",
                subject_id=run.id,
                run_id=run.id,
                notes="Component dropped: " + "; ".join(result.component_errors),
            )
        )
        audit.record(
            session,
            actor=None,
            action="run.component_failed",
            subject_type="RUN",
            subject_id=run.id,
            run_id=run.id,
            reason_code="COMPONENT_FAILED",
            details={"errors": list(result.component_errors)},
        )
    if not result.outcomes:
        finish_without_settlement(session, run, RunStatus.ABORTED, "NOTHING_TO_NET")
        return
    run.current_attempt += 1
    all_excluded = excluded | set(result.limit_excluded)
    computation = RunComputation(
        run_id=run.id,
        attempt=run.current_attempt,
        input_hash=result.input_hash,
        result_hash=result.result_hash,
        seed=str(result.seed),
        algo_version=settings.algo_version,
        excluded_members=sorted(str(m) for m in all_excluded),
        trigger=trigger,
        metrics={
            **result.metrics.as_dict(),
            "carries": jsonable_encoder([asdict(c) for c in result.carries]),
            "carry_in_used": jsonable_encoder([asdict(c) for c in result.carry_in_used]),
        },
    )
    session.add(computation)
    session.flush()
    for dropped in {d.invoice_id: d for d in result.dropped}.values():
        invoice = session.get(Invoice, dropped.invoice_id)
        assert invoice is not None
        party = next(
            (p for p in (invoice.payer_member_id, invoice.issuer_member_id) if p in all_excluded),
            None,
        )
        reason = {
            "LIMIT_EXCEEDED": ExclusionReason.LIMIT_EXCEEDED,
            "NO_RATE": ExclusionReason.NO_RATE,
            "COMPONENT_FAILED": ExclusionReason.COMPONENT_FAILED,
        }.get(dropped.reason, ExclusionReason.REJECTED_STATEMENT)
        if dropped.reason != "MEMBER_EXCLUDED":
            exclude(session, run, invoice, reason, party, computation.id)
        release(session, run, invoice, reason)
    for c in result.cancellations:
        session.add(
            Cancellation(
                computation_id=computation.id,
                invoice_id=c.invoice_id,
                cycle_no=c.cycle_no,
                amount_minor=c.amount_minor,
            )
        )
    for p in result.positions:
        session.add(
            NetPosition(
                computation_id=computation.id,
                party_type=p.party_type,
                member_id=p.member_id,
                currency=p.currency,
                amount_minor=p.amount_minor,
                gross_in_minor=p.gross_in_minor,
                gross_out_minor=p.gross_out_minor,
            )
        )
    for t in result.transfers:
        session.add(
            PlannedTransfer(
                computation_id=computation.id,
                payer_party=t.payer_type,
                payer_member_id=t.payer_member_id,
                receiver_party=t.receiver_type,
                receiver_member_id=t.receiver_member_id,
                currency=t.currency,
                amount_minor=t.amount_minor,
                kind=t.kind,
            )
        )
    for leg in result.fx_legs:
        session.add(FxLeg(computation_id=computation.id, **asdict(leg)))
    included_ids = {o.invoice_id for o in result.outcomes}
    pricing = pricing_inputs(
        (
            (i.payer_member_id, i.currency, i.outstanding_minor)
            for i in frozen
            if i.invoice_id in included_ids
        ),
        [(p.member_id, p.currency, p.amount_minor) for p in result.positions if p.member_id],
        rates,
        exponents,
    )
    fees = compute_fees(pricing, settings.standard_rate_bps, settings.fee_share_bps)
    for fee in fees.values():
        session.add(
            FeeCharge(
                computation_id=computation.id, price_version=settings.price_version, **asdict(fee)
            )
        )
    change(session, run, RunStatus.COMPUTED, None, trigger)
    emit(session, "run.computed", run.id, {"run_id": str(run.id)})
    if result.metrics.fallback_to_greedy:
        session.add(
            Case(
                type="ENGINE_ALERT",
                subject_type="RUN",
                subject_id=run.id,
                run_id=run.id,
                notes="Invalid improved plan; validated greedy plan used.",
            )
        )
        audit.record(
            session,
            actor=None,
            action="run.engine_fallback",
            subject_type="RUN",
            subject_id=run.id,
            run_id=run.id,
            reason_code="GREEDY_FALLBACK",
        )
    statements = build(session, run, computation, result, members, fees, exponents)
    for statement in statements:
        old = next(
            (
                s
                for s in old_statements
                if s.member_id == statement.member_id and s.content_hash == statement.content_hash
            ),
            None,
        )
        if old:
            for approval in session.scalars(
                select(Approval).where(
                    Approval.statement_id == old.id,
                    Approval.decision == "APPROVED",
                    Approval.content_hash == statement.content_hash,
                )
            ):
                session.add(
                    Approval(
                        statement_id=statement.id,
                        approver_id=approval.approver_id,
                        decision="APPROVED",
                        content_hash=statement.content_hash,
                        method="CARRIED_FORWARD",
                    )
                )
    change(session, run, RunStatus.AWAITING_APPROVAL, None, trigger)
    emit(
        session,
        "run.statements_issued",
        run.id,
        {"run_id": str(run.id), "member_ids": [str(s.member_id) for s in statements]},
    )
    if previous:
        emit(
            session,
            "run.recomputed",
            run.id,
            {"run_id": str(run.id), "member_ids": [str(s.member_id) for s in statements]},
        )
    session.flush()
    from app.modules.statements.service import maybe_approved

    maybe_approved(session, run.id)


def finish_without_settlement(
    session: Session,
    run: NettingRun,
    status: RunStatus,
    reason: str,
    actor: Principal | None = None,
) -> None:
    for i in session.scalars(
        select(Invoice)
        .join(RunInvoice, RunInvoice.invoice_id == Invoice.id)
        .where(RunInvoice.run_id == run.id)
        .order_by(Invoice.id)
    ):
        release(session, run, i, reason)
    change(session, run, status, actor, reason)
    emit(
        session,
        "run.fallback_gross" if status == RunStatus.FALLBACK_GROSS else "run.aborted",
        run.id,
        {
            "run_id": str(run.id),
            "reason": reason,
            "member_ids": sorted(
                {
                    str(i.payer_member_id)
                    for i in session.scalars(select(RunInvoice).where(RunInvoice.run_id == run.id))
                }
                | {
                    str(i.receiver_member_id)
                    for i in session.scalars(select(RunInvoice).where(RunInvoice.run_id == run.id))
                }
            ),
        },
    )


def recompute(
    session: Session,
    run: NettingRun,
    removed: Mapping[UUID, ExclusionReason],
    reason: str,
) -> None:
    """Exclude members and compute again (one exclusion event), or fall back after the cap.

    Rejections, expired approvals, funding failures and prepare-time screening hits all
    come through here, so they share the cap of MAX_RECOMPUTES re-runs (MC-APR-06).
    """
    current = repository.latest(session, run)
    assert current is not None
    excluded = {UUID(m) for m in current.excluded_members} | set(removed)
    locked = list(
        session.scalars(
            select(Invoice)
            .join(RunInvoice, RunInvoice.invoice_id == Invoice.id)
            .where(
                RunInvoice.run_id == run.id,
                RunInvoice.payer_member_id.in_(list(removed))
                | RunInvoice.receiver_member_id.in_(list(removed)),
                Invoice.status == InvoiceStatus.LOCKED_IN_RUN,
            )
            .order_by(Invoice.id)
        )
    )
    for i in locked:
        member_id = next(
            m for m in sorted(removed, key=str) if m in (i.payer_member_id, i.issuer_member_id)
        )
        exclude(session, run, i, removed[member_id], member_id, current.id)
        release(session, run, i, removed[member_id])
    if run.current_attempt >= min(get_settings().max_recomputes, 2) + 1:
        finish_without_settlement(session, run, RunStatus.FALLBACK_GROSS, "RECOMPUTE_CAP")
        return
    change(session, run, RunStatus.RECOMPUTING, None, reason)
    compute(session, run, excluded, reason)


def pricing_inputs(
    payables: Iterable[tuple[UUID, str, int]],
    positions: Iterable[tuple[UUID, str, int]],
    rates: Mapping[tuple[str, str], Decimal],
    exponents: Mapping[str, int],
) -> list[MemberPricingInput]:
    """Gross payables (each invoice converted on its own, then summed) and net payables.

    `payables` are (payer, currency, outstanding) for every included invoice; `positions`
    are (member, settlement currency, signed net). Runs, savings and estimates share this.
    """
    target = {m: c for m, c, _ in positions}
    gross: dict[UUID, int] = dict.fromkeys(target, 0)
    for payer, currency, outstanding in payables:
        if payer not in target:
            continue
        to = target[payer]
        rate = lookup_rate(rates, currency, to) if currency != to else Decimal(1)
        gross[payer] += convert_minor(outstanding, rate, exponents[currency], exponents[to])
    return [MemberPricingInput(m, c, gross[m], max(-amount, 0)) for m, c, amount in positions]


def get_admin(session: Session, run_id: UUID, lock: bool = False) -> NettingRun:
    query = select(NettingRun).where(NettingRun.id == run_id)
    run = session.scalar(query.with_for_update() if lock else query)
    if run is None:
        raise NotFound()
    return run
