"""Member reads. Every member-facing function takes the caller's member_id (layering rule 3)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import TERMINAL_RUN_STATES, InvoiceStatus, KillSwitchScope
from app.modules.invoices.models import Invoice
from app.modules.members.models import KillSwitch, LegalEntity, Member, User
from app.modules.runs.models import NettingRun
from app.modules.windows.models import RunInvoice


def get_member(session: Session, member_id: UUID) -> Member | None:
    return session.get(Member, member_id)


def get_member_with_entity(session: Session, member_id: UUID) -> tuple[Member, LegalEntity] | None:
    row = session.execute(
        select(Member, LegalEntity)
        .join(LegalEntity, LegalEntity.id == Member.legal_entity_id)
        .where(Member.id == member_id)
    ).one_or_none()
    return (row[0], row[1]) if row else None


def team(session: Session, member_id: UUID) -> list[User]:
    return list(
        session.scalars(select(User).where(User.member_id == member_id).order_by(User.email))
    )


def user_by_email(session: Session, email: str) -> User | None:
    return session.scalars(select(User).where(User.email == email.strip().lower())).one_or_none()


def kill_switch_on(session: Session, member_id: UUID | None = None) -> bool:
    """Global switch, or the member's switch when member_id is given."""
    query = select(KillSwitch.enabled).where(KillSwitch.scope == KillSwitchScope.GLOBAL)
    if member_id is not None:
        query = select(KillSwitch.enabled).where(
            KillSwitch.scope == KillSwitchScope.MEMBER, KillSwitch.member_id == member_id
        )
    return bool(session.scalar(query))


def in_active_run(session: Session, member_id: UUID) -> bool:
    """Whether the member still has invoices locked in a run that has not finished."""
    return bool(
        session.scalar(
            select(NettingRun.id)
            .join(RunInvoice, RunInvoice.run_id == NettingRun.id)
            .join(Invoice, Invoice.id == RunInvoice.invoice_id)
            .where(
                NettingRun.status.not_in(list(TERMINAL_RUN_STATES)),
                Invoice.status == InvoiceStatus.LOCKED_IN_RUN,
                (RunInvoice.payer_member_id == member_id)
                | (RunInvoice.receiver_member_id == member_id),
            )
            .limit(1)
        )
    )
