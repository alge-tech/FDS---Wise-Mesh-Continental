from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.invoices import repository, service
from app.modules.invoices.models import Invoice
from app.modules.invoices.schemas import CounterpartyView


def list_for_member(session: Session, member_id: UUID) -> list[CounterpartyView]:
    groups: dict[str, CounterpartyView] = {}
    for invoice in session.scalars(select(Invoice).where(repository.involves(member_id))):
        v = service.view(session, invoice, member_id)
        identity = v.payer_tax_id if v.direction == "RECEIVABLE" else v.issuer_tax_id
        if identity not in groups:
            groups[identity] = CounterpartyView(
                identity=identity,
                name=v.counterparty,
                member_id=v.counterparty_member_id,
                status="MATCHED" if v.counterparty_member_id else "UNMATCHED",
                invoice_count=0,
            )
        groups[identity].invoice_count += 1
    return sorted(groups.values(), key=lambda c: c.name)
