from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Identity, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, currency_col, fk, pk, status_check, timestamp_col
from app.core.enums import JournalKind, LedgerAccountType


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"

    id: Mapped[UUID] = pk()
    type: Mapped[str] = mapped_column(Text, nullable=False)
    member_id: Mapped[UUID | None] = fk("members.id", nullable=True)
    run_id: Mapped[UUID | None] = fk("netting_runs.id", nullable=True)
    currency: Mapped[str] = currency_col()
    created_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (
        status_check("type", LedgerAccountType),
        UniqueConstraint(
            "type", "member_id", "run_id", "currency", postgresql_nulls_not_distinct=True
        ),
    )


class JournalEntry(Base):
    """Insert-only. `seq` orders the hash chain; `hash` covers the entry and its postings."""

    __tablename__ = "journal_entries"

    id: Mapped[UUID] = pk()
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    run_id: Mapped[UUID | None] = fk("netting_runs.id", nullable=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    hash_prev: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = timestamp_col()

    __table_args__ = (status_check("kind", JournalKind),)


class Posting(Base):
    """Insert-only signed amount on one account. Each entry sums to zero per currency."""

    __tablename__ = "postings"

    id: Mapped[UUID] = pk()
    journal_entry_id: Mapped[UUID] = fk("journal_entries.id")
    account_id: Mapped[UUID] = fk("ledger_accounts.id")
    currency: Mapped[str] = currency_col()
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)  # signed

    __table_args__ = (CheckConstraint("amount_minor <> 0", name="non_zero"),)
