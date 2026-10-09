"""Add COMPONENT_FAILED to the invoice exclusion reasons (MC-NET-01).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = (
    "NOT_MATCHED",
    "NOT_CONFIRMED",
    "DISPUTED",
    "MEMBER_NOT_ACTIVE",
    "COUNTERPARTY_UNAVAILABLE",
    "NO_RATE",
    "OUTSIDE_HORIZON",
    "KILL_SWITCH",
    "AGREEMENT_PENDING",
    "SANCTIONS_HIT",
    "HOLD_FOR_REVIEW",
    "LIMIT_EXCEEDED",
    "WITHDRAWN",
    "REJECTED_STATEMENT",
    "APPROVAL_EXPIRED",
    "FUNDING_FAILED",
    "UNDER_REVIEW",
)
AFTER = (*BEFORE, "COMPONENT_FAILED")


def _replace_checks(reasons: tuple[str, ...]) -> None:
    values = ", ".join(f"'{r}'" for r in reasons)
    for column in ("internal_reason", "public_reason"):
        name = f"ck_invoice_exclusions_{column}_valid"
        op.drop_constraint(op.f(name), "invoice_exclusions", type_="check")
        op.create_check_constraint(op.f(name), "invoice_exclusions", f"{column} IN ({values})")


def upgrade() -> None:
    _replace_checks(AFTER)


def downgrade() -> None:
    op.execute(
        "DELETE FROM invoice_exclusions WHERE 'COMPONENT_FAILED' IN (internal_reason, public_reason)"
    )
    _replace_checks(BEFORE)
