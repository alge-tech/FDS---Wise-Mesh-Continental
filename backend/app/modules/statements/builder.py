from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.hashing import hash_canonical
from app.core.ids import utcnow
from app.core.money import format_minor
from app.modules.audit import service as audit
from app.modules.invoices.models import Invoice
from app.modules.members.models import LegalEntity, Member
from app.modules.netting.types import EngineResult
from app.modules.pricing.calc import FeeLine
from app.modules.runs.models import NettingRun, RunComputation
from app.modules.statements.models import Statement


def build(
    session: Session,
    run: NettingRun,
    computation: RunComputation,
    result: EngineResult,
    members: dict[UUID, Member],
    fees: dict[UUID, FeeLine],
    exponents: dict[str, int],
) -> list[Statement]:
    settings = get_settings()
    outcomes = {o.invoice_id: o for o in result.outcomes}
    invoices = {i.id: i for i in session.scalars(select(Invoice).where(Invoice.id.in_(outcomes)))}
    names = {
        m.id: session.get(LegalEntity, m.legal_entity_id).legal_name  # type: ignore[union-attr]
        for m in members.values()
    }
    statements = []
    for member_id, fee in sorted(fees.items(), key=lambda item: str(item[0])):
        member = members[member_id]
        p = next(p for p in result.positions if p.member_id == member_id)
        own = []
        for invoice_id, outcome in sorted(outcomes.items(), key=lambda item: str(item[0])):
            i = invoices[invoice_id]
            if member_id not in {i.payer_member_id, i.issuer_member_id}:
                continue
            payable = i.payer_member_id == member_id
            other = i.issuer_member_id if payable else i.payer_member_id
            own.append(
                {
                    "invoice_id": str(i.id),
                    "invoice_number": i.invoice_number,
                    "version": i.current_version,
                    "counterparty": names[other],  # type: ignore[index]
                    "direction": "PAYABLE" if payable else "RECEIVABLE",
                    "currency": i.currency,
                    "outstanding_minor": outcome.outstanding_minor,
                    "cancelled_minor": outcome.cancelled_minor,
                    "residual_minor": outcome.residual_minor,
                }
            )
        ffr = min(fee.fee_minor, max(p.amount_minor, 0))
        debit = max(-p.amount_minor, 0) + fee.fee_minor - ffr
        credit = max(p.amount_minor, 0) - ffr
        value = format_minor(debit if debit else credit, exponents[p.currency])
        summary = (
            f"You will pay {p.currency} {value}, including the Mesh fee."
            if debit
            else f"You will receive {p.currency} {value}, after the Mesh fee."
            if credit
            else "Your invoices net to zero; no payment is needed."
        )
        summary += (
            " Approve these terms to take part."
            " If you do nothing, settlement waits for your approval."
        )
        content: dict[str, Any] = {
            "summary": summary,
            "settlement_currency": p.currency,
            "invoices": own,
            "gross_payable": {
                c: sum(
                    i["outstanding_minor"]
                    for i in own
                    if i["direction"] == "PAYABLE" and i["currency"] == c
                )
                for c in sorted({i["currency"] for i in own})
            },
            "gross_receivable": {
                c: sum(
                    i["outstanding_minor"]
                    for i in own
                    if i["direction"] == "RECEIVABLE" and i["currency"] == c
                )
                for c in sorted({i["currency"] for i in own})
            },
            "net_minor": p.amount_minor,
            "carried_minor": p.carried_minor,
            "debit_minor": debit,
            "credit_minor": credit,
            "counterparty": "Mesh settlement",
            # Rates travel as strings: a Decimal must never pass through a float.
            "fx_legs": [
                {
                    "from_currency": leg.from_currency,
                    "from_amount_minor": leg.from_amount_minor,
                    "to_currency": leg.to_currency,
                    "to_amount_minor": leg.to_amount_minor,
                    "rate": format(leg.rate.normalize(), "f"),
                }
                for leg in result.fx_legs
                if leg.member_id == member_id
            ],
            "pricing": {
                "baseline_minor": fee.baseline_minor,
                "actual_minor": fee.actual_minor,
                "savings_minor": fee.savings_minor,
                "fee_minor": fee.fee_minor,
                "net_benefit_minor": fee.net_benefit_minor,
                "price_version": settings.price_version,
                "standard_rate_bps": settings.standard_rate_bps,
                "fee_share_bps": settings.fee_share_bps,
            },
            "rules_version": settings.rules_version,
        }
        above = (
            member.maker_checker_minor is not None
            and max(-p.amount_minor, 0) > member.maker_checker_minor
        )
        statement = Statement(
            computation_id=computation.id,
            member_id=member_id,
            content=content,
            content_hash=hash_canonical(content),
            required_approvers=2 if above else 1,
            expires_at=utcnow() + timedelta(minutes=settings.fx_lock_minutes),
        )
        session.add(statement)
        session.flush()
        audit.record(
            session,
            actor=None,
            action="statement.issued",
            subject_type="STATEMENT",
            subject_id=statement.id,
            run_id=run.id,
            after={"content_hash": statement.content_hash},
        )
        statements.append(statement)
    return statements
