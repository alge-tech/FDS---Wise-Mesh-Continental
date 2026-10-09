from dataclasses import asdict, replace
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.enums import (
    ConfirmationDecision,
    ConfirmationMethod,
    ExclusionReason,
    InvoiceSource,
    InvoiceStatus,
)
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.security import Principal
from app.events.outbox import emit
from app.modules.audit import service as audit
from app.modules.audit.models import AuditEvent
from app.modules.confirmations.models import Confirmation
from app.modules.fx.models import Currency
from app.modules.invoices import repository, state
from app.modules.invoices.models import Invoice, InvoiceVersion
from app.modules.invoices.parsing import ParsedInvoice, RowError, normalise_tax_id, validate_row
from app.modules.invoices.schemas import InvoiceCreate, InvoiceDetail, InvoiceView
from app.modules.members.models import LegalEntity, Member
from app.modules.settlement.models import InvoiceOutcome
from app.modules.windows.eligibility import public_reason
from app.modules.windows.models import InvoiceExclusion


def exponents(session: Session) -> dict[str, int]:
    return dict(session.execute(select(Currency.code, Currency.exponent)).tuples().all())


def parse(session: Session, body: InvoiceCreate) -> ParsedInvoice:
    result = validate_row(body.model_dump(), 1, exponents(session))
    if isinstance(result, list):
        raise ValidationFailed(
            "Check the invoice fields.", details={"rows": [asdict(e) for e in result]}
        )
    return result


def match(session: Session, identity: str) -> tuple[LegalEntity | None, Member | None]:
    rows = session.execute(
        select(LegalEntity, Member).outerjoin(Member, Member.legal_entity_id == LegalEntity.id)
    ).all()
    found = [
        (e, m)
        for e, m in rows
        if identity in {normalise_tax_id(e.tax_id), normalise_tax_id(e.registration_no or "")}
    ]
    if len(found) > 1:
        raise ValidationFailed("The party identity is ambiguous.")
    return found[0] if found else (None, None)


def create(
    session: Session,
    parsed: ParsedInvoice,
    member_id: UUID,
    actor: Principal | None,
    source: InvoiceSource,
) -> Invoice:
    issuer, issuer_member = match(session, parsed.issuer_tax_id)
    payer, payer_member = match(session, parsed.payer_tax_id)
    parties = {m.id for m in (issuer_member, payer_member) if m is not None}
    if member_id not in parties:
        raise ValidationFailed("You must be the issuer or payer.")
    if issuer_member and payer_member and issuer_member.id == payer_member.id:
        raise ValidationFailed("The issuer and payer must be different businesses.")
    parsed = replace(
        parsed,
        issuer_tax_id=normalise_tax_id(issuer.tax_id) if issuer else parsed.issuer_tax_id,
        payer_tax_id=normalise_tax_id(payer.tax_id) if payer else parsed.payer_tax_id,
    )
    # Serialise same-fingerprint uploads before testing the unique key.
    session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(parsed.fingerprint[:15], 16)}
    )
    existing = repository.by_fingerprint(session, parsed.fingerprint)
    if existing:
        raise Conflict("This invoice has already been uploaded.", code="DUPLICATE_INVOICE")
    invoice = Invoice(
        issuer_entity_id=issuer.id if issuer else None,
        payer_entity_id=payer.id if payer else None,
        issuer_member_id=issuer_member.id if issuer_member else None,
        payer_member_id=payer_member.id if payer_member else None,
        uploader_member_id=member_id,
        counterparty_raw={
            "issuer_tax_id": issuer.tax_id if issuer else parsed.issuer_tax_id,
            "payer_tax_id": payer.tax_id if payer else parsed.payer_tax_id,
        },
        invoice_number=parsed.invoice_number,
        issue_date=parsed.issue_date,
        due_date=parsed.due_date,
        currency=parsed.currency,
        amount_minor=parsed.amount_minor,
        outstanding_minor=parsed.outstanding_minor,
        fingerprint=parsed.fingerprint,
        source=source,
        created_by=actor.user_id if actor else None,
    )
    session.add(invoice)
    session.flush()
    session.add(
        InvoiceVersion(
            invoice_id=invoice.id,
            version=1,
            change_type="CREATED",
            changed_fields=jsonable_encoder(asdict(parsed)),
            actor_id=actor.user_id if actor else None,
        )
    )
    audit.record(
        session,
        actor=actor,
        action="invoice.imported",
        subject_type="INVOICE",
        subject_id=invoice.id,
        after={"version": 1},
        reason_code="INGEST",
    )
    if issuer_member and payer_member:
        state.transition(session, invoice, InvoiceStatus.MATCHED, actor=actor)
        state.transition(session, invoice, InvoiceStatus.PENDING_CONFIRMATION, actor=actor)
        session.add(
            Confirmation(
                invoice_id=invoice.id,
                version=1,
                party_member_id=member_id,
                decision=ConfirmationDecision.CONFIRMED,
                method=ConfirmationMethod.AUTO,
                actor_id=actor.user_id if actor else None,
            )
        )
        other = next(p for p in parties if p != member_id)
        emit(
            session,
            "invoice.confirmation_requested",
            invoice.id,
            {"member_id": str(other), "invoice_id": str(invoice.id), "version": 1},
        )
    else:
        state.transition(session, invoice, InvoiceStatus.UNMATCHED, actor=actor)
    session.flush()
    return invoice


def view(session: Session, invoice: Invoice, member_id: UUID) -> InvoiceView:
    receivable = invoice.issuer_member_id == member_id
    other = invoice.payer_member_id if receivable else invoice.issuer_member_id
    entity_id = invoice.payer_entity_id if receivable else invoice.issuer_entity_id
    entity = session.get(LegalEntity, entity_id) if entity_id else None
    decisions = list(
        session.scalars(
            select(Confirmation).where(
                Confirmation.invoice_id == invoice.id,
                Confirmation.version == invoice.current_version,
                Confirmation.party_member_id == member_id,
            )
        )
    )
    return InvoiceView(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        currency=invoice.currency,
        amount_minor=invoice.amount_minor,
        outstanding_minor=invoice.outstanding_minor,
        status=invoice.status,
        current_version=invoice.current_version,
        direction="RECEIVABLE" if receivable else "PAYABLE",
        counterparty=entity.legal_name
        if entity
        else invoice.counterparty_raw["payer_tax_id" if receivable else "issuer_tax_id"],
        counterparty_member_id=other,
        issuer_tax_id=invoice.counterparty_raw["issuer_tax_id"],
        payer_tax_id=invoice.counterparty_raw["payer_tax_id"],
        needs_confirmation=invoice.status == InvoiceStatus.PENDING_CONFIRMATION and not decisions,
    )


def detail(session: Session, member_id: UUID, invoice_id: UUID) -> InvoiceDetail:
    invoice = repository.get_for_member(session, member_id, invoice_id)
    if invoice is None:
        raise NotFound()
    confirmations = list(
        session.scalars(
            select(Confirmation)
            .where(Confirmation.invoice_id == invoice.id)
            .order_by(Confirmation.created_at)
        )
    )
    exclusions = list(
        session.scalars(
            select(InvoiceExclusion)
            .where(InvoiceExclusion.invoice_id == invoice.id)
            .order_by(InvoiceExclusion.created_at)
        )
    )
    events = list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.subject_type == "INVOICE", AuditEvent.subject_id == invoice.id)
            .order_by(AuditEvent.created_at)
        )
    )
    outcomes = list(
        session.scalars(select(InvoiceOutcome).where(InvoiceOutcome.invoice_id == invoice.id))
    )
    return InvoiceDetail(
        **view(session, invoice, member_id).model_dump(),
        versions=[
            {"version": v.version, "change_type": v.change_type, "changed_fields": v.changed_fields}
            for v in repository.versions(session, invoice.id)
        ],
        confirmations=[
            {
                "version": c.version,
                "party_member_id": str(c.party_member_id),
                "decision": c.decision,
                "method": c.method,
                "reason_code": c.reason_code,
            }
            for c in confirmations
        ],
        # The reason as this viewer may see it: its own reason, or a neutral one for the
        # counterparty (sanctions and review holds are never shown as such).
        exclusions=[
            {
                "run_id": str(e.run_id),
                "reason": public_reason(
                    ExclusionReason(e.internal_reason), e.excluded_member_id, member_id
                ),
            }
            for e in exclusions
        ],
        outcomes=[
            {
                "run_id": str(o.run_id),
                "outcome": o.outcome,
                "cancelled_minor": o.cancelled_minor,
                "residual_minor": o.residual_minor,
            }
            for o in outcomes
        ],
        # Do not expose system risk details or actor identities to counterparties.
        audit=[{"action": e.action, "created_at": e.created_at.isoformat()} for e in events],
    )


def upload(session: Session, content: bytes, member_id: UUID, actor: Principal) -> dict[str, Any]:
    from app.core.config import get_settings
    from app.modules.invoices.parsing import CsvShapeError, read_csv

    settings = get_settings()
    if len(content) > settings.csv_max_bytes:
        raise ValidationFailed("The CSV must be 5 MB or smaller.")
    try:
        rows = list(read_csv(content, settings.csv_max_rows))
    except CsvShapeError as exc:
        raise ValidationFailed(str(exc)) from exc
    errors: list[RowError] = []
    items: list[InvoiceView] = []
    for row_no, raw in rows:
        parsed = validate_row(raw, row_no, exponents(session))
        if isinstance(parsed, list):
            errors.extend(parsed)
            continue
        try:
            with session.begin_nested():
                invoice = create(session, parsed, member_id, actor, InvoiceSource.CSV)
                items.append(view(session, invoice, member_id))
        except (Conflict, ValidationFailed) as exc:
            errors.append(RowError(row_no, "invoice", exc.code + ": " + str(exc)))
    return {"items": items, "errors": [asdict(e) for e in errors]}
