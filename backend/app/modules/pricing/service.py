"""Savings and estimates. Both reuse the pricing used for statements, so the numbers match."""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import RunStatus
from app.core.errors import NotFound
from app.core.schemas import money
from app.modules.fx.models import Currency
from app.modules.members.models import Member
from app.modules.pricing.calc import MemberPricingInput, compute_fees
from app.modules.pricing.models import FeeCharge
from app.modules.pricing.schemas import (
    Estimate,
    EstimateRequest,
    SavingsItem,
    SavingsSummary,
    SavingsTotal,
)
from app.modules.runs import repository
from app.modules.runs import service as runs
from app.modules.runs.models import NettingRun, RunComputation
from app.modules.statements.models import Statement


def _exponents(session: Session) -> dict[str, int]:
    return dict(session.execute(select(Currency.code, Currency.exponent)).tuples().all())


def pricing_inputs(
    session: Session, run: NettingRun, statements: list[Statement]
) -> list[MemberPricingInput]:
    """Each statement's own invoices and net, priced exactly as the computation priced them."""
    payables = [
        (s.member_id, str(i["currency"]), int(i["outstanding_minor"]))
        for s in statements
        for i in s.content["invoices"]
        if i["direction"] == "PAYABLE"
    ]
    positions = [
        (s.member_id, str(s.content["settlement_currency"]), int(s.content["net_minor"]))
        for s in statements
    ]
    return runs.pricing_inputs(
        payables, positions, runs.snapshot_rates(session, run.id), _exponents(session)
    )


def _statement(session: Session, computation: RunComputation, member_id: UUID) -> Statement | None:
    return session.scalar(
        select(Statement).where(
            Statement.computation_id == computation.id, Statement.member_id == member_id
        )
    )


def savings(session: Session, member_id: UUID) -> SavingsSummary:
    items: list[SavingsItem] = []
    for run in repository.list_for_member(session, member_id):
        if run.status in (RunStatus.ABORTED, RunStatus.FALLBACK_GROSS):
            continue  # nothing was netted: the invoices went back for gross payment
        computation = repository.latest(session, run)
        statement = _statement(session, computation, member_id) if computation else None
        fee = (
            session.scalar(
                select(FeeCharge).where(
                    FeeCharge.computation_id == computation.id, FeeCharge.member_id == member_id
                )
            )
            if computation
            else None
        )
        if statement is None or fee is None:
            continue
        [own] = pricing_inputs(session, run, [statement])
        c, settled = statement.content, run.status == RunStatus.COMMITTED
        items.append(
            SavingsItem(
                run_id=run.id,
                status=run.status,
                settled=settled,
                settled_at=run.finished_at if settled else None,
                currency=fee.currency,
                gross_payable=money(own.gross_payable_minor, fee.currency),
                net_paid=money(int(c["debit_minor"]), fee.currency),
                net_received=money(int(c["credit_minor"]), fee.currency),
                baseline=money(fee.baseline_minor, fee.currency),
                actual=money(fee.actual_minor, fee.currency),
                fee=money(fee.fee_minor, fee.currency),
                savings=money(fee.baseline_minor - fee.actual_minor, fee.currency),
                price_version=fee.price_version,
            )
        )
    sums: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item in items:
        if not item.settled:
            continue
        t = sums[item.currency]
        t["runs"] += 1
        for field in ("gross_payable", "net_paid", "baseline", "actual", "fee", "savings"):
            t[field] += getattr(item, field).amount_minor
    totals = [
        SavingsTotal(
            currency=currency,
            runs=t["runs"],
            **{
                f: money(t[f], currency)
                for f in ("gross_payable", "net_paid", "baseline", "actual", "fee", "savings")
            },
        )
        for currency, t in sorted(sums.items())
    ]
    return SavingsSummary(items=items, totals=totals)


def estimate(session: Session, member_id: UUID, body: EstimateRequest) -> Estimate:
    """No stored data changes. A run estimate re-allocates the fee across the whole run."""
    if body.run_id is not None:
        run = repository.get_for_member(session, member_id, UUID(body.run_id))
        computation = repository.latest(session, run) if run else None
        if (
            run is None
            or computation is None
            or _statement(session, computation, member_id) is None
        ):
            raise NotFound()
        statements = list(
            session.scalars(select(Statement).where(Statement.computation_id == computation.id))
        )
        inputs = pricing_inputs(session, run, statements)
        source, run_id = "RUN", run.id
    else:
        member = session.get(Member, member_id)
        assert member is not None
        assert body.gross_payable_minor is not None and body.net_payable_minor is not None
        inputs = [
            MemberPricingInput(
                member_id,
                member.settlement_currency,
                body.gross_payable_minor,
                body.net_payable_minor,
            )
        ]
        source, run_id = "INPUT", None
    line = compute_fees(inputs, body.standard_rate_bps, body.fee_share_bps)[member_id]
    own = next(i for i in inputs if i.member_id == member_id)
    cur = line.currency
    return Estimate(
        source=source,
        run_id=run_id,
        currency=cur,
        standard_rate_bps=body.standard_rate_bps,
        fee_share_bps=body.fee_share_bps,
        gross_payable=money(own.gross_payable_minor, cur),
        net_payable=money(own.net_payable_minor, cur),
        baseline=money(line.baseline_minor, cur),
        actual=money(line.actual_minor, cur),
        fee=money(line.fee_minor, cur),
        gross_savings=money(line.savings_minor, cur),
        savings=money(line.net_benefit_minor, cur),
        # The fee is a share of savings, so Mesh only costs as much as gross at a 100% share.
        break_even_fee_share_bps=10_000 if line.savings_minor > 0 else None,
    )
