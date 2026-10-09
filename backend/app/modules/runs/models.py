from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, currency_col, fk, pk, status_check, timestamp_col
from app.core.enums import PartyType, RunStatus, TransferKind, TransferStatus


class NettingRun(Base):
    __tablename__ = "netting_runs"

    id: Mapped[UUID] = pk()
    window_id: Mapped[UUID] = fk("windows.id")
    status: Mapped[str] = mapped_column(Text, nullable=False, default=RunStatus.FROZEN)
    current_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = timestamp_col()
    finished_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (UniqueConstraint("window_id"), status_check("status", RunStatus))


class RunComputation(Base):
    """One engine attempt. A re-computation adds a row; earlier attempts stay auditable."""

    __tablename__ = "run_computations"

    id: Mapped[UUID] = pk()
    run_id: Mapped[UUID] = fk("netting_runs.id")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    excluded_members: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    algo_version: Mapped[str] = mapped_column(Text, nullable=False)
    seed: Mapped[str] = mapped_column(Text, nullable=False)
    result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (
        UniqueConstraint("run_id", "attempt"),
        CheckConstraint("attempt BETWEEN 1 AND 3", name="attempt_range"),
    )


class Cancellation(Base):
    __tablename__ = "cancellations"

    id: Mapped[UUID] = pk()
    computation_id: Mapped[UUID] = fk("run_computations.id")
    invoice_id: Mapped[UUID] = fk("invoices.id")
    cycle_no: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (CheckConstraint("amount_minor > 0", name="amount_positive"),)


class NetPosition(Base):
    """Signed position (positive = receives). FX and CARRY are pseudo-parties with no member."""

    __tablename__ = "net_positions"

    id: Mapped[UUID] = pk()
    computation_id: Mapped[UUID] = fk("run_computations.id")
    party_type: Mapped[str] = mapped_column(Text, nullable=False, default=PartyType.MEMBER)
    member_id: Mapped[UUID | None] = fk("members.id", nullable=True)
    currency: Mapped[str] = currency_col()
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)  # signed
    gross_in_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    gross_out_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        status_check("party_type", PartyType),
        CheckConstraint("(party_type = 'MEMBER') = (member_id IS NOT NULL)", name="party"),
    )


class PlannedTransfer(Base):
    __tablename__ = "planned_transfers"

    id: Mapped[UUID] = pk()
    computation_id: Mapped[UUID] = fk("run_computations.id")
    payer_party: Mapped[str] = mapped_column(Text, nullable=False, default=PartyType.MEMBER)
    payer_member_id: Mapped[UUID | None] = fk("members.id", nullable=True, index=False)
    receiver_party: Mapped[str] = mapped_column(Text, nullable=False, default=PartyType.MEMBER)
    receiver_member_id: Mapped[UUID | None] = fk("members.id", nullable=True, index=False)
    currency: Mapped[str] = currency_col()
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, default=TransferKind.SETTLEMENT)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=TransferStatus.PLANNED)

    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        status_check("payer_party", PartyType),
        status_check("receiver_party", PartyType),
        status_check("kind", TransferKind),
        status_check("status", TransferStatus),
    )


class FxLeg(Base):
    """A member's off-currency position converted into its settlement currency."""

    __tablename__ = "fx_legs"

    id: Mapped[UUID] = pk()
    computation_id: Mapped[UUID] = fk("run_computations.id")
    member_id: Mapped[UUID] = fk("members.id")
    from_currency: Mapped[str] = currency_col()
    from_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)  # signed
    to_currency: Mapped[str] = currency_col()
    to_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)  # signed
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)


class Withdrawal(Base):
    __tablename__ = "withdrawals"

    id: Mapped[UUID] = pk()
    run_id: Mapped[UUID] = fk("netting_runs.id")
    member_id: Mapped[UUID] = fk("members.id")
    invoice_id: Mapped[UUID] = fk("invoices.id")
    created_by: Mapped[UUID] = fk("users.id", index=False)
    created_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (UniqueConstraint("run_id", "invoice_id"),)
