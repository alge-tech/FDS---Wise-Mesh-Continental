from datetime import datetime
from uuid import UUID

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, fk, pk, status_check, timestamp_col
from app.core.enums import InvitationStatus


class Invitation(Base):
    """Mock invitation of an unmatched counterparty (MC-ENT-02). No email is sent."""

    __tablename__ = "invitations"

    id: Mapped[UUID] = pk()
    from_member_id: Mapped[UUID] = fk("members.id")
    invoice_id: Mapped[UUID] = fk("invoices.id")
    contact_email: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=InvitationStatus.PENDING)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (status_check("status", InvitationStatus),)
