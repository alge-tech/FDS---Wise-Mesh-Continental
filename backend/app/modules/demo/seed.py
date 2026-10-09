"""Base seed (MC-ONB-01, MC-LED-03): members A-F, users per role, rates, opening balances.

Invoices are not seeded here; load them with a scenario (worked_example, ...) or the
synthetic generator so the demo can show the upload and confirmation flow.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import Base
from app.core.enums import (
    JournalKind,
    KillSwitchScope,
    LedgerAccountType,
    MemberState,
    Role,
    WindowStatus,
)
from app.core.security import hash_password
from app.modules.demo.scenarios import MEMBERS, NON_MEMBER_ENTITY, SANCTIONED_ENTITY
from app.modules.fx.models import Currency, FxRate
from app.modules.ledger import service as ledger
from app.modules.ledger.postings import AccountRef, PostingLine
from app.modules.members.models import KillSwitch, LegalEntity, Member, User
from app.modules.risk.models import SanctionsEntry
from app.modules.windows.models import Window

CURRENCIES = [
    ("EUR", 2, "Euro"),
    ("USD", 2, "US dollar"),
    ("HUF", 2, "Hungarian forint"),
    ("GBP", 2, "Pound sterling"),
    ("CNY", 2, "Chinese yuan"),
]

RATE_SOURCE = "Static demo table (illustrative mid-market, 2026-10-01)"
RATES = [
    ("EUR", "USD", "1.0850"),
    ("EUR", "GBP", "0.8450"),
    ("EUR", "HUF", "395.10"),
    ("EUR", "CNY", "7.7800"),
    ("USD", "GBP", "0.7790"),
    ("USD", "CNY", "7.1700"),
    ("GBP", "HUF", "467.60"),
]

STAFF = [
    ("ops@wise.test", "Olivia Ops", Role.WISE_OPS),
    ("compliance@wise.test", "Chris Compliance", Role.WISE_COMPLIANCE),
]

MEMBER_USERS = [
    ("admin", "Admin", Role.MEMBER_ADMIN),
    ("finance", "Finance", Role.FINANCE_USER),
    ("approver", "Approver", Role.APPROVER),
]


# Seeded users keep the same ID across demo resets, so a session that clicks "Reset" (and
# every other open demo browser) stays logged in. Everything else gets fresh UUIDv7s.
_SEED_NAMESPACE = UUID("6f3b7a52-6d65-7368-8000-000000000000")


def seed_user_id(email: str) -> UUID:
    return uuid5(_SEED_NAMESPACE, email)


def member_email(code: str, kind: str) -> str:
    return f"{kind}@member-{code.lower()}.test"


def is_seeded(session: Session) -> bool:
    return session.scalar(select(Currency.code).limit(1)) is not None


def seed(session: Session) -> None:
    """Insert the base data. Call inside a transaction on an empty database."""
    settings = get_settings()
    password_hash = hash_password(settings.demo_password)
    valid_from = datetime(2026, 10, 1, tzinfo=UTC)

    session.add_all(Currency(code=c, exponent=e, name=n) for c, e, n in CURRENCIES)
    session.flush()
    session.add_all(
        FxRate(base=b, quote=q, rate=Decimal(r), source=RATE_SOURCE, valid_from=valid_from)
        for b, q, r in RATES
    )

    for code_entity in (NON_MEMBER_ENTITY, SANCTIONED_ENTITY):
        session.add(LegalEntity(**code_entity))
    session.add(
        SanctionsEntry(
            name=SANCTIONED_ENTITY["legal_name"],
            country=SANCTIONED_ENTITY["country"],
            tax_id=SANCTIONED_ENTITY["tax_id"],
            source="Mock consolidated list (demo)",
        )
    )

    for email, name, role in STAFF:
        session.add(
            User(
                id=seed_user_id(email),
                email=email,
                display_name=name,
                password_hash=password_hash,
                role=role,
            )
        )

    session.add(KillSwitch(scope=KillSwitchScope.GLOBAL, enabled=False, reason="initial"))

    for m in MEMBERS:
        entity = LegalEntity(
            legal_name=m.legal_name,
            tax_id=m.tax_id,
            registration_no=m.registration_no,
            country=m.country,
        )
        session.add(entity)
        session.flush()
        member = Member(
            legal_entity_id=entity.id,
            display_name=m.display_name,
            state=MemberState.ACTIVE,
            settlement_currency=m.settlement_currency,
            payable_limit_minor=m.payable_limit_major * 100 if m.payable_limit_major else None,
            maker_checker_minor=m.maker_checker_major * 100 if m.maker_checker_major else None,
            agreement_version="2026-10",
        )
        session.add(member)
        session.flush()
        for kind, label, role in MEMBER_USERS:
            session.add(
                User(
                    id=seed_user_id(member_email(m.code, kind)),
                    member_id=member.id,
                    email=member_email(m.code, kind),
                    display_name=f"{m.display_name} {label}",
                    password_hash=password_hash,
                    role=role,
                )
            )
        for currency, major in sorted(m.opening_balances_major.items()):
            amount = major * 100
            ledger.post(
                session,
                kind=JournalKind.OPENING,
                idempotency_key=f"opening:{m.code}:{currency}",
                lines=[
                    PostingLine(
                        AccountRef(LedgerAccountType.MEMBER_BALANCE, member.id, currency), amount
                    ),
                    PostingLine(AccountRef(LedgerAccountType.SUSPENSE, None, currency), -amount),
                ],
            )

    session.add(Window(status=WindowStatus.OPEN, rules_version=settings.rules_version))
    session.flush()


def truncate_all(owner_session: Session) -> None:
    """Wipe every table. Runs as the owner role; the append-only triggers allow it only here."""
    tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    owner_session.execute(text("SET LOCAL mesh.allow_reset = 'on'"))
    owner_session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
