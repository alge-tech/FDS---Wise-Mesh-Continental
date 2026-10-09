from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, currency_col, fk, pk, status_check, timestamp_col
from app.core.enums import HoldStatus, InvoiceOutcomeKind, JobStatus, SettlementStep


class Hold(Base):
    __tablename__ = "holds"

    id: Mapped[UUID] = pk()
    run_id: Mapped[UUID] = fk("netting_runs.id")
    member_id: Mapped[UUID] = fk("members.id")
    currency: Mapped[str] = currency_col()
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=HoldStatus.ACTIVE)
    journal_entry_id: Mapped[UUID] = fk("journal_entries.id", index=False)
    release_entry_id: Mapped[UUID | None] = fk("journal_entries.id", nullable=True, index=False)
    created_at: Mapped[datetime] = timestamp_col()
    updated_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        status_check("status", HoldStatus),
        UniqueConstraint("run_id", "member_id", "currency"),
    )


class SettlementJob(Base):
    """Written before and after each step, so Settle can resume (crash safety)."""

    __tablename__ = "settlement_jobs"

    id: Mapped[UUID] = pk()
    run_id: Mapped[UUID] = fk("netting_runs.id")
    member_id: Mapped[UUID | None] = fk("members.id", nullable=True, index=False)
    step: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=JobStatus.STARTED)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = timestamp_col()
    updated_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (status_check("step", SettlementStep), status_check("status", JobStatus))


class InvoiceOutcome(Base):
    __tablename__ = "invoice_outcomes"

    id: Mapped[UUID] = pk()
    invoice_id: Mapped[UUID] = fk("invoices.id")
    run_id: Mapped[UUID] = fk("netting_runs.id")
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    outstanding_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cancelled_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    residual_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (
        UniqueConstraint("invoice_id", "run_id"),
        status_check("outcome", InvoiceOutcomeKind),
        CheckConstraint(
            "cancelled_minor >= 0 AND residual_minor >= 0 "
            "AND cancelled_minor + residual_minor = outstanding_minor",
            name="g6_balance",
        ),
        CheckConstraint(
            "(outcome = 'SETTLED_BY_NETTING') = (residual_minor = 0)", name="outcome_matches"
        ),
    )
