from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, currency_col, fk, pk, status_check, timestamp_col
from app.core.enums import ExclusionReason, WindowStatus


class Window(Base):
    __tablename__ = "windows"

    id: Mapped[UUID] = pk()
    status: Mapped[str] = mapped_column(Text, nullable=False, default=WindowStatus.OPEN)
    opened_at: Mapped[datetime] = timestamp_col()
    closed_at: Mapped[datetime | None] = mapped_column()
    horizon_days: Mapped[int | None] = mapped_column(Integer)  # None = all due dates (demo)
    rules_version: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        status_check("status", WindowStatus),
        Index(
            "uq_windows_one_open", "status", unique=True, postgresql_where=text("status = 'OPEN'")
        ),
    )


class RunInvoice(Base):
    """The frozen set. Terms are copied so prepare can recompute the input hash exactly."""

    __tablename__ = "run_invoices"

    run_id: Mapped[UUID] = mapped_column(ForeignKey("netting_runs.id"), primary_key=True)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payer_member_id: Mapped[UUID] = fk("members.id", index=False)
    receiver_member_id: Mapped[UUID] = fk("members.id", index=False)
    currency: Mapped[str] = currency_col()
    outstanding_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (CheckConstraint("outstanding_minor > 0", name="outstanding_positive"),)


class InvoiceExclusion(Base):
    """Why an invoice was left out of a run, at freeze or at a re-computation.

    `public_reason` is what the counterparty may see (never a sanctions hit or a funding
    failure of the other side); `internal_reason` is for Wise staff.
    """

    __tablename__ = "invoice_exclusions"

    id: Mapped[UUID] = pk()
    window_id: Mapped[UUID] = fk("windows.id")
    run_id: Mapped[UUID | None] = fk("netting_runs.id", nullable=True)
    computation_id: Mapped[UUID | None] = fk("run_computations.id", nullable=True)
    invoice_id: Mapped[UUID] = fk("invoices.id")
    excluded_member_id: Mapped[UUID | None] = fk("members.id", nullable=True, index=False)
    public_reason: Mapped[str] = mapped_column(Text, nullable=False)
    internal_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (
        status_check("public_reason", ExclusionReason),
        status_check("internal_reason", ExclusionReason),
    )
