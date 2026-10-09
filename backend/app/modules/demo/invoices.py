"""Deterministic demo ingestion uses the same services as real member uploads."""

from datetime import date
from random import Random
from typing import Any, Literal

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ConfirmationMethod, InvoiceSource
from app.core.errors import Conflict, NotFound
from app.core.schemas import StrictModel
from app.core.security import Principal
from app.modules.audit import service as audit
from app.modules.confirmations import service as confirmations
from app.modules.confirmations.models import Confirmation
from app.modules.demo.scenarios import MEMBERS, SCENARIOS
from app.modules.invoices import service
from app.modules.invoices.models import Invoice
from app.modules.invoices.parsing import ParsedInvoice
from app.modules.invoices.schemas import ConfirmationRequest
from app.modules.members.models import LegalEntity, Member


class Simulate(StrictModel):
    confirm_pct: int = Field(default=100, ge=0, le=100)
    dispute_pct: int = Field(default=0, ge=0, le=100)
    seed: int = 1

    @model_validator(mode="after")
    def percentages(self) -> "Simulate":
        if self.confirm_pct + self.dispute_pct > 100:
            raise ValueError("Confirmation and dispute percentages must total at most 100.")
        return self


class Generate(StrictModel):
    members: int = Field(default=6, ge=2, le=1000)
    invoices: int = Field(default=30, ge=1, le=20000)
    currencies: list[str] = Field(default_factory=lambda: ["EUR"], min_length=1)
    cycle_density: int = Field(default=50, ge=0, le=100)
    seed: int = 1


def scenario(session: Session, name: str, actor: Principal) -> dict[str, Any]:
    if name not in SCENARIOS:
        raise NotFound("Unknown scenario.")
    entities = {
        e.tax_id: m
        for e, m in session.execute(
            select(LegalEntity, Member).join(Member, Member.legal_entity_id == LegalEntity.id)
        )
    }
    specs = {m.code: m for m in MEMBERS}
    ids = []
    for i in SCENARIOS[name]:
        parsed = ParsedInvoice(
            1,
            i.invoice_number,
            specs[i.issuer].tax_id,
            specs[i.payer].tax_id,
            i.currency,
            i.amount_major * 100,
            i.amount_major * 100,
            date.fromisoformat(i.issue_date),
            date.fromisoformat(i.due_date),
        )
        try:
            with session.begin_nested():
                row = service.create(
                    session,
                    parsed,
                    entities[specs[i.issuer].tax_id].id,
                    actor,
                    InvoiceSource.SCENARIO,
                )
                ids.append(str(row.id))
        except Conflict as exc:
            if exc.code != "DUPLICATE_INVOICE":
                raise
    audit.record(
        session,
        actor=actor,
        action="demo.scenario",
        subject_type="SYSTEM",
        subject_id=actor.user_id,
        reason_code="DEMO_SCENARIO",
        details={"scenario": name},
    )
    return {"created": len(ids), "invoice_ids": ids}


def simulate(session: Session, body: Simulate, actor: Principal) -> dict[str, int]:
    rng = Random(body.seed)
    counts = {"confirmed": 0, "disputed": 0, "pending": 0}
    rows = list(
        session.scalars(
            select(Invoice).where(Invoice.status == "PENDING_CONFIRMATION").order_by(Invoice.id)
        )
    )
    for i in rows:
        existing = set(
            session.scalars(
                select(Confirmation.party_member_id).where(
                    Confirmation.invoice_id == i.id, Confirmation.version == i.current_version
                )
            )
        )
        for member_id in sorted({i.payer_member_id, i.issuer_member_id} - existing, key=str):
            assert member_id is not None
            draw = rng.randrange(100)
            decision: Literal["CONFIRM", "DISPUTE"] | None = (
                "CONFIRM"
                if draw < body.confirm_pct
                else ("DISPUTE" if draw < body.confirm_pct + body.dispute_pct else None)
            )
            if decision:
                confirmations.decide(
                    session,
                    member_id,
                    i.id,
                    ConfirmationRequest(
                        decision=decision,
                        version=i.current_version,
                        reason_code="OTHER" if decision == "DISPUTE" else None,
                    ),
                    actor,
                    ConfirmationMethod.SIMULATED,
                )
            if i.status == "DISPUTED":
                break
        counts[{"CONFIRMED": "confirmed", "DISPUTED": "disputed"}.get(i.status, "pending")] += 1
    audit.record(
        session,
        actor=actor,
        action="demo.simulate_confirmations",
        subject_type="SYSTEM",
        subject_id=actor.user_id,
        reason_code="DEMO_SIMULATION",
        details=body.model_dump(),
    )
    return counts


def generate(session: Session, body: Generate, actor: Principal) -> dict[str, int]:
    from app.core.errors import ValidationFailed

    exps = service.exponents(session)
    if any(c not in exps for c in body.currencies):
        raise ValidationFailed("Choose supported currencies.")
    db_rows = list(
        session.execute(
            select(Member, LegalEntity)
            .join(LegalEntity, Member.legal_entity_id == LegalEntity.id)
            .order_by(Member.id)
        )
    )
    rows = [(m, e) for m, e in db_rows]
    for index in range(len(rows), body.members):
        tax_id = f"DEGEN{body.seed:08d}{index:04d}"
        entity = LegalEntity(
            legal_name=f"Generated Business {body.seed}-{index + 1}", tax_id=tax_id, country="DE"
        )
        session.add(entity)
        session.flush()
        member = Member(
            legal_entity_id=entity.id,
            display_name=entity.legal_name,
            settlement_currency="EUR",
            agreement_version="2026-10",
        )
        session.add(member)
        session.flush()
        rows.append((member, entity))
    rows = rows[: body.members]
    rng = Random(body.seed)
    created = 0
    for index in range(body.invoices):
        a = index % len(rows)
        b = (
            (a + 1) % len(rows)
            if rng.randrange(100) < body.cycle_density
            else rng.randrange(len(rows) - 1)
        )
        if b == a:
            b = len(rows) - 1
        payer, issuer = rows[a], rows[b]
        currency = rng.choice(body.currencies)
        amount = rng.randrange(100, 10001) * 10 ** exps[currency]
        parsed = ParsedInvoice(
            1,
            f"GEN-{body.seed}-{index}",
            issuer[1].tax_id,
            payer[1].tax_id,
            currency,
            amount,
            amount,
            date(2026, 10, 1),
            date(2026, 10, 31),
        )
        try:
            with session.begin_nested():
                service.create(session, parsed, issuer[0].id, actor, InvoiceSource.GENERATED)
                created += 1
        except Conflict as exc:
            if exc.code != "DUPLICATE_INVOICE":
                raise
    audit.record(
        session,
        actor=actor,
        action="demo.generate",
        subject_type="SYSTEM",
        subject_id=actor.user_id,
        reason_code="DEMO_GENERATE",
        details=body.model_dump(),
    )
    return {"created": created, "members": len(rows)}
