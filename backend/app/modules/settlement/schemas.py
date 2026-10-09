from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.core.schemas import ApiModel, Money, StrictModel

MESH_COUNTERPARTY = "Mesh settlement"


class ReasonRequest(StrictModel):
    """Every Wise staff action carries a reason code (MC-OPS-01)."""

    reason_code: str = Field(min_length=1, max_length=200)

    @field_validator("reason_code")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A reason is required.")
        return value.strip()


class LedgerLine(ApiModel):
    """One of the member's own ledger movements. The counterparty is always Mesh settlement."""

    entry_kind: str  # HOLD, COMMIT or RELEASE
    account: Literal["BALANCE", "HELD", "CARRIED"]
    description: str
    amount: Money  # signed: negative leaves the account
    counterparty: str = MESH_COUNTERPARTY
    created_at: datetime


class MemberSettlement(ApiModel):
    """The member's own side of settlement (MC-PRV-02): no other member is ever named."""

    status: Literal["PENDING", "FUNDS_HELD", "SETTLED", "CANCELLED"]
    instruction: Literal["DEBIT", "CREDIT", "NONE"]
    amount: Money
    counterparty: str = MESH_COUNTERPARTY
    reference: str
    held: Money | None
    carried: Money | None
    settled_by_netting: int
    settled_by_transfer: int
    ledger: list[LedgerLine]


class HoldView(ApiModel):
    member_id: UUID
    member_name: str
    currency: str
    amount_minor: int
    status: str


class JobView(ApiModel):
    step: str
    member_id: UUID | None
    status: str
    attempts: int
    last_error: str | None
    result: dict[str, Any] | None
    updated_at: datetime


class TransferView(ApiModel):
    payer: str
    receiver: str
    currency: str
    amount_minor: int
    kind: str
    status: str


class AccountBalance(ApiModel):
    currency: str
    balance_minor: int


class SettlementDetail(ApiModel):
    """Wise staff view of a run's settlement: holds, jobs, transfers and clearing."""

    holds: list[HoldView]
    jobs: list[JobView]
    transfers: list[TransferView]
    clearing: list[AccountBalance]
    commit_entry_seq: int | None


class ClearingBreak(ApiModel):
    run_id: UUID
    account_type: str
    currency: str
    balance_minor: int


class LedgerCheck(ApiModel):
    ok: bool
    entries: int
    chain_ok: bool
    first_break_seq: int | None
    unbalanced_entries: list[int]
    clearing_ok: bool
    breaks: list[ClearingBreak]
    active_holds: int
    checked_at: datetime
