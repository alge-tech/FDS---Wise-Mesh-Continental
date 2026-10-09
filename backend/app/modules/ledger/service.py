"""Append-only double-entry ledger (MC-LED-01..03).

Entries are only ever inserted. Each entry's postings sum to zero per currency, and each
entry stores the previous entry's hash, so `check_chain` can detect any edit.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.enums import JournalKind, LedgerAccountType
from app.core.hashing import hash_canonical
from app.core.ids import new_id
from app.modules.ledger.models import JournalEntry, LedgerAccount, Posting
from app.modules.ledger.postings import AccountRef, PostingLine, sum_by_currency

GENESIS_HASH = "0" * 64
_CHAIN_LOCK_KEY = 7_202_610  # pg_advisory_xact_lock key that serialises chain appends


class LedgerImbalance(RuntimeError):
    pass


def get_account(session: Session, ref: AccountRef, run_id: UUID | None = None) -> LedgerAccount:
    scoped_run = run_id if ref.run_scoped else None
    if ref.run_scoped and run_id is None:
        raise ValueError(f"{ref.type} accounts are per run")
    query = select(LedgerAccount).where(
        LedgerAccount.type == ref.type,
        LedgerAccount.currency == ref.currency,
        LedgerAccount.member_id.is_(None)
        if ref.member_id is None
        else LedgerAccount.member_id == ref.member_id,
        LedgerAccount.run_id.is_(None)
        if scoped_run is None
        else LedgerAccount.run_id == scoped_run,
    )
    account = session.scalars(query).one_or_none()
    if account is not None:
        return account
    session.execute(
        pg_insert(LedgerAccount)
        .values(
            id=new_id(),
            type=ref.type,
            member_id=ref.member_id,
            run_id=scoped_run,
            currency=ref.currency,
        )
        .on_conflict_do_nothing()
    )
    return session.scalars(query).one()


def _entry_hash(
    entry_id: UUID,
    kind: str,
    run_id: UUID | None,
    key: str,
    hash_prev: str,
    postings: Iterable[tuple[UUID, str, int]],
) -> str:
    return hash_canonical(
        {
            "id": entry_id,
            "kind": kind,
            "run_id": run_id,
            "idempotency_key": key,
            "hash_prev": hash_prev,
            "postings": sorted([str(a), c, amt] for a, c, amt in postings),
        }
    )


def post(
    session: Session,
    *,
    kind: JournalKind,
    lines: list[PostingLine],
    idempotency_key: str,
    run_id: UUID | None = None,
) -> JournalEntry:
    """Insert one balanced journal entry. Re-posting the same key returns the stored entry."""
    existing = session.scalars(
        select(JournalEntry).where(JournalEntry.idempotency_key == idempotency_key)
    ).one_or_none()
    if existing is not None:
        return existing
    if not lines:
        raise LedgerImbalance("a journal entry needs postings")
    unbalanced = {c: v for c, v in sum_by_currency(lines).items() if v != 0}
    if unbalanced:
        raise LedgerImbalance(f"postings don't sum to zero: {unbalanced}")

    session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CHAIN_LOCK_KEY})
    last = session.scalars(select(JournalEntry).order_by(JournalEntry.seq.desc()).limit(1)).first()
    hash_prev = last.hash if last else GENESIS_HASH

    resolved = [
        (get_account(session, line.account, run_id).id, line.account.currency, line.amount_minor)
        for line in lines
    ]
    entry_id = new_id()
    entry = JournalEntry(
        id=entry_id,
        run_id=run_id,
        kind=kind,
        idempotency_key=idempotency_key,
        hash_prev=hash_prev,
        hash=_entry_hash(entry_id, kind, run_id, idempotency_key, hash_prev, resolved),
    )
    session.add(entry)
    session.flush()
    session.add_all(
        Posting(journal_entry_id=entry_id, account_id=a, currency=c, amount_minor=amt)
        for a, c, amt in resolved
    )
    session.flush()
    return entry


@dataclass(frozen=True)
class Balance:
    currency: str
    available_minor: int
    held_minor: int


def member_balances(session: Session, member_id: UUID) -> list[Balance]:
    """Balances are derived from postings only (MC-LED-03)."""
    rows = session.execute(
        select(
            LedgerAccount.type, Posting.currency, func.coalesce(func.sum(Posting.amount_minor), 0)
        )
        .join(Posting, Posting.account_id == LedgerAccount.id)
        .where(
            LedgerAccount.member_id == member_id,
            LedgerAccount.type.in_(
                [LedgerAccountType.MEMBER_BALANCE, LedgerAccountType.MEMBER_HOLD]
            ),
        )
        .group_by(LedgerAccount.type, Posting.currency)
    ).all()
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"a": 0, "h": 0})
    for account_type, currency, amount in rows:
        slot = "a" if account_type == LedgerAccountType.MEMBER_BALANCE else "h"
        totals[currency][slot] += int(amount)
    return [Balance(c, t["a"], t["h"]) for c, t in sorted(totals.items())]


def lock_balance(session: Session, member_id: UUID, currency: str) -> int:
    """Lock a member's balance account (SELECT ... FOR UPDATE) and return its balance.

    Prepare holds this lock until it has posted the hold, so two runs can never both
    spend the same available funds.
    """
    account = get_account(
        session, AccountRef(LedgerAccountType.MEMBER_BALANCE, member_id, currency)
    )
    session.execute(
        select(LedgerAccount.id).where(LedgerAccount.id == account.id).with_for_update()
    )
    return account_balance(session, account.id)


def account_balance(session: Session, account_id: UUID) -> int:
    return int(
        session.scalar(
            select(func.coalesce(func.sum(Posting.amount_minor), 0)).where(
                Posting.account_id == account_id
            )
        )
        or 0
    )


def run_account_balances(
    session: Session, run_id: UUID, account_type: LedgerAccountType
) -> dict[tuple[UUID | None, str], int]:
    rows = session.execute(
        select(LedgerAccount.member_id, LedgerAccount.currency, func.sum(Posting.amount_minor))
        .join(Posting, Posting.account_id == LedgerAccount.id)
        .where(LedgerAccount.run_id == run_id, LedgerAccount.type == account_type)
        .group_by(LedgerAccount.member_id, LedgerAccount.currency)
    ).all()
    return {(m, c): int(v) for m, c, v in rows}


@dataclass(frozen=True)
class ChainReport:
    entries: int
    ok: bool
    first_break_seq: int | None
    unbalanced_entries: list[int]


def check_chain(session: Session) -> ChainReport:
    """Walk every entry in order: re-hash it, check the link and that it balances."""
    postings: dict[UUID, list[tuple[UUID, str, int]]] = defaultdict(list)
    for p in session.scalars(select(Posting)):
        postings[p.journal_entry_id].append((p.account_id, p.currency, p.amount_minor))
    prev = GENESIS_HASH
    first_break: int | None = None
    unbalanced: list[int] = []
    count = 0
    for entry in session.scalars(select(JournalEntry).order_by(JournalEntry.seq)):
        count += 1
        lines = postings.get(entry.id, [])
        expected = _entry_hash(
            entry.id, entry.kind, entry.run_id, entry.idempotency_key, entry.hash_prev, lines
        )
        if first_break is None and (entry.hash_prev != prev or entry.hash != expected):
            first_break = entry.seq
        by_currency: dict[str, int] = defaultdict(int)
        for _, currency, amount in lines:
            by_currency[currency] += amount
        if any(v != 0 for v in by_currency.values()):
            unbalanced.append(entry.seq)
        prev = entry.hash
    return ChainReport(count, first_break is None and not unbalanced, first_break, unbalanced)
