from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CHAR, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.db import Base, fk, pk, status_check, timestamp_col
from app.core.enums import CaseStatus, CaseType, RiskDecisionKind


class SanctionsEntry(Base):
    """Mock sanctions list. Matched on tax ID, or on normalised legal name plus country."""

    __tablename__ = "sanctions_list"

    id: Mapped[UUID] = pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    tax_id: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = timestamp_col()


class RiskDecision(Base):
    __tablename__ = "risk_decisions"

    id: Mapped[UUID] = pk()
    run_id: Mapped[UUID | None] = fk("netting_runs.id", nullable=True)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    rule: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    reasons: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (status_check("decision", RiskDecisionKind),)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[UUID] = pk()
    type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    run_id: Mapped[UUID | None] = fk("netting_runs.id", nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=CaseStatus.OPEN)
    assignee_id: Mapped[UUID | None] = fk("users.id", nullable=True, index=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = timestamp_col()
    updated_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (status_check("type", CaseType), status_check("status", CaseStatus))
