from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ConfirmationMethod, InvoiceStatus
from app.core.errors import Conflict, InvalidState, NotFound, ValidationFailed
from app.core.money import format_minor
from app.core.security import Principal
from app.events.outbox import emit
from app.modules.audit import service as audit
from app.modules.confirmations.models import Confirmation
from app.modules.invoices import repository, service, state
from app.modules.invoices.models import Invoice, InvoiceVersion
from app.modules.invoices.parsing import validate_row
from app.modules.invoices.schemas import ConfirmationRequest


def decide(
    session: Session,
    member_id: UUID,
    invoice_id: UUID,
    body: ConfirmationRequest,
    actor: Principal | None,
    method: ConfirmationMethod = ConfirmationMethod.USER,
) -> Invoice:
    invoice = repository.get_for_member(session, member_id, invoice_id, for_update=True)
    if invoice is None:
        raise NotFound()
    if invoice.current_version != body.version:
        raise Conflict(
            "The invoice terms have changed. Reload them.",
            code="INVOICE_CHANGED",
            details={"current_version": invoice.current_version},
        )
    if invoice.status not in state.EDITABLE:
        raise InvalidState("This invoice cannot be confirmed or corrected now.")
    if body.decision == "CORRECT":
        if not body.corrected_fields or not body.corrected_fields.model_dump(exclude_none=True):
            raise ValidationFailed("Provide corrected fields.")
        exponent = service.exponents(session)[invoice.currency]
        raw = {
            "invoice_number": invoice.invoice_number,
            **invoice.counterparty_raw,
            "currency": invoice.currency,
            "amount": format_minor(invoice.amount_minor, exponent),
            "outstanding": format_minor(invoice.outstanding_minor, exponent),
            "issue_date": invoice.issue_date.isoformat(),
            "due_date": invoice.due_date.isoformat(),
            **body.corrected_fields.model_dump(exclude_none=True),
        }
        parsed = validate_row(raw, 1, service.exponents(session))
        if isinstance(parsed, list):
            raise ValidationFailed("Check the corrected terms.")
        duplicate = repository.by_fingerprint(session, parsed.fingerprint)
        if duplicate is not None and duplicate.id != invoice.id:
            raise Conflict("The correction duplicates another invoice.", code="DUPLICATE_INVOICE")
        state.transition(
            session,
            invoice,
            InvoiceStatus.AMENDED,
            actor=actor,
            reason_code=body.reason_code or "CORRECTION",
        )
        invoice.current_version += 1
        invoice.amount_minor = parsed.amount_minor
        invoice.outstanding_minor = parsed.outstanding_minor
        invoice.due_date = parsed.due_date
        invoice.invoice_number = parsed.invoice_number
        invoice.fingerprint = parsed.fingerprint
        session.add(
            InvoiceVersion(
                invoice_id=invoice.id,
                version=invoice.current_version,
                change_type="CORRECTED",
                changed_fields=body.corrected_fields.model_dump(exclude_none=True),
                actor_id=actor.user_id if actor else None,
            )
        )
        state.transition(session, invoice, InvoiceStatus.PENDING_CONFIRMATION, actor=actor)
        # Neither side's old confirmation counts for the new terms.
        emit(
            session,
            "invoice.confirmation_requested",
            invoice.id,
            {
                "member_ids": [str(invoice.payer_member_id), str(invoice.issuer_member_id)],
                "invoice_id": str(invoice.id),
                "version": invoice.current_version,
            },
        )
    else:
        if invoice.status == InvoiceStatus.DISPUTED:
            raise InvalidState("Correct the disputed terms before confirming a new version.")
        previous = session.scalar(
            select(Confirmation).where(
                Confirmation.invoice_id == invoice.id,
                Confirmation.version == body.version,
                Confirmation.party_member_id == member_id,
            )
        )
        if previous:
            raise Conflict("You have already answered this version.", code="ALREADY_CONFIRMED")
        if body.decision == "DISPUTE" and not body.reason_code:
            raise ValidationFailed("Choose a dispute reason.")
        decision = "CONFIRMED" if body.decision == "CONFIRM" else "DISPUTED"
        session.add(
            Confirmation(
                invoice_id=invoice.id,
                version=body.version,
                party_member_id=member_id,
                decision=decision,
                reason_code=body.reason_code,
                method=method,
                actor_id=actor.user_id if actor else None,
            )
        )
        session.flush()
        audit.record(
            session,
            actor=actor,
            action="invoice.party_decision",
            subject_type="INVOICE",
            subject_id=invoice.id,
            after={"decision": decision, "version": body.version},
            reason_code=body.reason_code or "CONFIRMATION",
        )
        confirmed = set(
            session.scalars(
                select(Confirmation.party_member_id).where(
                    Confirmation.invoice_id == invoice.id,
                    Confirmation.version == body.version,
                    Confirmation.decision == "CONFIRMED",
                )
            )
        )
        if decision == "DISPUTED":
            state.transition(
                session, invoice, InvoiceStatus.DISPUTED, actor=actor, reason_code=body.reason_code
            )
            emit(
                session,
                "invoice.disputed",
                invoice.id,
                {"member_ids": [str(invoice.payer_member_id), str(invoice.issuer_member_id)]},
            )
        elif confirmed == {invoice.payer_member_id, invoice.issuer_member_id}:
            state.transition(session, invoice, InvoiceStatus.CONFIRMED, actor=actor)
            emit(
                session,
                "invoice.confirmed",
                invoice.id,
                {"member_ids": [str(invoice.payer_member_id), str(invoice.issuer_member_id)]},
            )
    session.flush()
    return invoice


def inbox(session: Session, member_id: UUID) -> list[Invoice]:
    decisions = (
        select(Confirmation.invoice_id)
        .where(
            Confirmation.party_member_id == member_id,
            Confirmation.version == Invoice.current_version,
        )
        .correlate(Invoice)
    )
    return list(
        session.scalars(
            select(Invoice)
            .where(
                repository.involves(member_id),
                Invoice.status == InvoiceStatus.PENDING_CONFIRMATION,
                ~Invoice.id.in_(decisions),
            )
            .order_by(Invoice.id)
        )
    )
