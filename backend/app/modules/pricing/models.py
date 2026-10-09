from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, currency_col, fk, pk


class FeeCharge(Base):
    """Gain-share pricing per member per computation, in the member's settlement currency."""

    __tablename__ = "fee_charges"

    id: Mapped[UUID] = pk()
    computation_id: Mapped[UUID] = fk("run_computations.id")
    member_id: Mapped[UUID] = fk("members.id")
    currency: Mapped[str] = currency_col()
    baseline_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    savings_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price_version: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("computation_id", "member_id"),
        CheckConstraint(
            "baseline_minor >= 0 AND actual_minor >= 0 AND savings_minor >= 0 AND fee_minor >= 0",
            name="non_negative",
        ),
        CheckConstraint("fee_minor <= savings_minor", name="fee_within_savings"),
    )
