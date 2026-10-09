from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, fk, pk, status_check, timestamp_col
from app.core.enums import ApprovalDecision, ApprovalMethod


class Statement(Base):
    """One per member per computation. `content_hash` covers the economic content only."""

    __tablename__ = "statements"

    id: Mapped[UUID] = pk()
    computation_id: Mapped[UUID] = fk("run_computations.id")
    member_id: Mapped[UUID] = fk("members.id")
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    required_approvers: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    issued_at: Mapped[datetime] = timestamp_col()
    expires_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (UniqueConstraint("computation_id", "member_id"),)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[UUID] = pk()
    statement_id: Mapped[UUID] = fk("statements.id")
    approver_id: Mapped[UUID] = fk("users.id", index=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False, default=ApprovalMethod.USER)
    created_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (
        UniqueConstraint("statement_id", "approver_id"),
        status_check("decision", ApprovalDecision),
        status_check("method", ApprovalMethod),
    )
