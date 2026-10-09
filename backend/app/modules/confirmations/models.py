from datetime import datetime
from uuid import UUID

from sqlalchemy import Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, fk, pk, status_check, timestamp_col
from app.core.enums import ConfirmationDecision, ConfirmationMethod


class Confirmation(Base):
    """One party's decision on one invoice version. Append-only.

    A correction creates a new invoice version, so confirmations of older versions stop
    counting without being touched (MC-CNF-04).
    """

    __tablename__ = "confirmations"

    id: Mapped[UUID] = pk()
    invoice_id: Mapped[UUID] = fk("invoices.id")
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    party_member_id: Mapped[UUID] = fk("members.id")
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[UUID | None] = fk("users.id", nullable=True, index=False)
    created_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (
        UniqueConstraint("invoice_id", "version", "party_member_id"),
        status_check("decision", ConfirmationDecision),
        status_check("method", ConfirmationMethod),
    )
