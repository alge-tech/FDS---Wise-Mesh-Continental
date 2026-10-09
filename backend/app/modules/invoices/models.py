from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, currency_col, fk, pk, status_check, timestamp_col
from app.core.enums import InvoiceSource, InvoiceStatus, VersionChange


class Invoice(Base):
    """Current state of an invoice. The issuer is owed money by the payer.

    Member IDs are denormalised from the legal entities so every member-facing query can
    be scoped with a plain WHERE clause.
    """

    __tablename__ = "invoices"

    id: Mapped[UUID] = pk()
    issuer_entity_id: Mapped[UUID | None] = fk("legal_entities.id", nullable=True)
    payer_entity_id: Mapped[UUID | None] = fk("legal_entities.id", nullable=True)
    issuer_member_id: Mapped[UUID | None] = fk("members.id", nullable=True)
    payer_member_id: Mapped[UUID | None] = fk("members.id", nullable=True)
    uploader_member_id: Mapped[UUID] = fk("members.id")
    counterparty_raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    invoice_number: Mapped[str] = mapped_column(Text, nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = currency_col()
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outstanding_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=InvoiceStatus.IMPORTED)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[UUID | None] = fk("users.id", nullable=True, index=False)
    created_at: Mapped[datetime] = timestamp_col()
    updated_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (
        status_check("status", InvoiceStatus),
        status_check("source", InvoiceSource),
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        CheckConstraint(
            "outstanding_minor >= 0 AND outstanding_minor <= amount_minor", name="outstanding"
        ),
        CheckConstraint("due_date >= issue_date", name="dates"),
        CheckConstraint(
            "issuer_member_id IS NULL OR payer_member_id IS NULL "
            "OR issuer_member_id <> payer_member_id",
            name="distinct_parties",
        ),
    )


class InvoiceVersion(Base):
    """Append-only history. Version 1 holds the full initial terms; later versions the diff."""

    __tablename__ = "invoice_versions"

    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    change_type: Mapped[str] = mapped_column(Text, nullable=False)
    changed_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    actor_id: Mapped[UUID | None] = fk("users.id", nullable=True, index=False)
    created_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (status_check("change_type", VersionChange),)
