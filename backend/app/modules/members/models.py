from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, currency_col, fk, pk, status_check, timestamp_col
from app.core.enums import KillSwitchScope, MemberState, RiskTier, Role


class LegalEntity(Base):
    __tablename__ = "legal_entities"

    id: Mapped[UUID] = pk()
    legal_name: Mapped[str] = mapped_column(Text, nullable=False)
    tax_id: Mapped[str] = mapped_column(Text, nullable=False)
    registration_no: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    created_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (UniqueConstraint("tax_id", "country"),)


class Member(Base):
    __tablename__ = "members"

    id: Mapped[UUID] = pk()
    legal_entity_id: Mapped[UUID] = fk("legal_entities.id")
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, default=MemberState.ACTIVE)
    risk_tier: Mapped[str] = mapped_column(Text, nullable=False, default=RiskTier.LOW)
    settlement_currency: Mapped[str] = currency_col()
    payable_limit_minor: Mapped[int | None] = mapped_column(BigInteger)
    maker_checker_minor: Mapped[int | None] = mapped_column(BigInteger)
    agreement_version: Mapped[str | None] = mapped_column(Text)
    # Demo control (MC-SET-03): when true, prepare treats the member as unable to fund.
    funding_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (
        UniqueConstraint("legal_entity_id"),
        status_check("state", MemberState),
        status_check("risk_tier", RiskTier),
        CheckConstraint("payable_limit_minor IS NULL OR payable_limit_minor >= 0", name="limit"),
        CheckConstraint("maker_checker_minor IS NULL OR maker_checker_minor >= 0", name="mc"),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = pk()
    member_id: Mapped[UUID | None] = fk("members.id", nullable=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (
        status_check("role", Role),
        CheckConstraint(
            "(role IN ('WISE_OPS', 'WISE_COMPLIANCE')) = (member_id IS NULL)",
            name="staff_have_no_member",
        ),
    )


class KillSwitch(Base):
    """Current switch state, one row per scope (and member). History lives in audit_events."""

    __tablename__ = "kill_switches"

    id: Mapped[UUID] = pk()
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    member_id: Mapped[UUID | None] = fk("members.id", nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[UUID | None] = fk("users.id", nullable=True, index=False)
    changed_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (
        status_check("scope", KillSwitchScope),
        CheckConstraint("(scope = 'GLOBAL') = (member_id IS NULL)", name="scope_member"),
        Index(
            "uq_kill_switches_global",
            "scope",
            unique=True,
            postgresql_where=text("scope = 'GLOBAL'"),
        ),
        Index(
            "uq_kill_switches_member",
            "member_id",
            unique=True,
            postgresql_where=text("scope = 'MEMBER'"),
        ),
    )
