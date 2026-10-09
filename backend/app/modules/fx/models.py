from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CHAR, CheckConstraint, Numeric, SmallInteger, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, currency_col, fk, pk, timestamp_col

RATE = Numeric(20, 10)


class Currency(Base):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(CHAR(3), primary_key=True)
    exponent: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (CheckConstraint("exponent BETWEEN 0 AND 4", name="exponent_range"),)


class FxRate(Base):
    """Static rate table: 1 unit of `base` buys `rate` units of `quote`."""

    __tablename__ = "fx_rates"

    id: Mapped[UUID] = pk()
    base: Mapped[str] = currency_col()
    quote: Mapped[str] = currency_col()
    rate: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("base", "quote", "valid_from"),
        CheckConstraint("rate > 0", name="rate_positive"),
        CheckConstraint("base <> quote", name="distinct_pair"),
    )


class RateSnapshot(Base):
    """Rates copied to a run at freeze (computation_id set when a recompute re-prices)."""

    __tablename__ = "rate_snapshots"

    id: Mapped[UUID] = pk()
    run_id: Mapped[UUID] = fk("netting_runs.id")
    computation_id: Mapped[UUID | None] = fk("run_computations.id", nullable=True)
    base: Mapped[str] = currency_col()
    quote: Mapped[str] = currency_col()
    rate: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (CheckConstraint("rate > 0", name="rate_positive"),)


class FxLock(Base):
    __tablename__ = "fx_locks"

    id: Mapped[UUID] = pk()
    run_id: Mapped[UUID] = fk("netting_runs.id")
    member_id: Mapped[UUID] = fk("members.id")
    base: Mapped[str] = currency_col()
    quote: Mapped[str] = currency_col()
    rate: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = timestamp_col()
