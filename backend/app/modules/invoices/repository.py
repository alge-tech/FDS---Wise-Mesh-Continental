"""Invoice reads. Member-facing functions take the caller's member_id and filter on it."""

from uuid import UUID

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from app.modules.invoices.models import Invoice, InvoiceVersion


def involves(member_id: UUID) -> ColumnElement[bool]:
    return or_(
        Invoice.issuer_member_id == member_id,
        Invoice.payer_member_id == member_id,
        Invoice.uploader_member_id == member_id,
    )


def get_for_member(
    session: Session, member_id: UUID, invoice_id: UUID, *, for_update: bool = False
) -> Invoice | None:
    query = select(Invoice).where(Invoice.id == invoice_id, involves(member_id))
    if for_update:
        query = query.with_for_update()
    return session.scalars(query).one_or_none()


def by_fingerprint(session: Session, fp: str) -> Invoice | None:
    return session.scalars(select(Invoice).where(Invoice.fingerprint == fp)).one_or_none()


def list_for_member(
    session: Session,
    member_id: UUID,
    *,
    direction: str | None,
    statuses: list[str] | None,
    counterparty: UUID | None,
    limit: int,
    cursor: UUID | None,
) -> list[Invoice]:
    query = select(Invoice).where(involves(member_id))
    # The uploader's own side always carries its member ID, so direction is just which side.
    if direction == "RECEIVABLE":
        query = query.where(Invoice.issuer_member_id == member_id)
    elif direction == "PAYABLE":
        query = query.where(Invoice.payer_member_id == member_id)
    if statuses:
        query = query.where(Invoice.status.in_(statuses))
    if counterparty is not None:
        query = query.where(
            or_(Invoice.issuer_member_id == counterparty, Invoice.payer_member_id == counterparty)
        )
    if cursor is not None:
        query = query.where(Invoice.id < cursor)
    return list(session.scalars(query.order_by(Invoice.id.desc()).limit(limit)))


def versions(session: Session, invoice_id: UUID) -> list[InvoiceVersion]:
    return list(
        session.scalars(
            select(InvoiceVersion)
            .where(InvoiceVersion.invoice_id == invoice_id)
            .order_by(InvoiceVersion.version)
        )
    )
