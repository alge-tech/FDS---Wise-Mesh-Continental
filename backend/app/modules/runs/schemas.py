from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.core.schemas import ApiModel, Money, StrictModel
from app.modules.settlement.schemas import MemberSettlement, SettlementDetail

CONTENT_HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"


class CloseRequest(StrictModel):
    reason_code: str = Field(min_length=1, max_length=200)

    @field_validator("reason_code")
    @classmethod
    def reason_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A reason is required.")
        return value.strip()


class ApprovalRequest(StrictModel):
    decision: Literal["APPROVE", "REJECT"]
    content_hash: str = Field(pattern=CONTENT_HASH_PATTERN)
    reason_code: str | None = None


UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class WithdrawalRequest(CloseRequest):
    """MC-APR-03: invoices from the caller's current statement, plus a reason."""

    invoice_ids: list[Annotated[str, Field(pattern=UUID_PATTERN)]] = Field(
        min_length=1, max_length=500
    )


class KillRequest(StrictModel):
    scope: Literal["GLOBAL", "MEMBER"]
    member_id: str | None = None
    enabled: bool
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def valid_scope(self) -> "KillRequest":
        if (self.scope == "MEMBER") != (self.member_id is not None):
            raise ValueError("Member scope requires a member ID; global scope has none.")
        if self.member_id is not None:
            UUID(self.member_id)
        if not self.reason.strip():
            raise ValueError("A reason is required.")
        return self


class WindowView(ApiModel):
    id: UUID
    opened_at: datetime
    horizon_days: int | None
    eligible_count: int
    excluded_count: int
    eligible_invoice_ids: list[UUID]
    exclusions: list[dict[str, Any]]


class RunView(ApiModel):
    id: UUID
    status: str
    current_attempt: int
    started_at: datetime
    statement_id: UUID | None = None
    content_hash: str | None = None
    own_positions: list[dict[str, Any]] = Field(default_factory=list)
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    computations: list[dict[str, Any]] = Field(default_factory=list)
    status_reason: str | None = None
    finished_at: datetime | None = None
    # The member's own settlement with Mesh settlement (member views only).
    settlement: MemberSettlement | None = None
    # Holds, jobs, transfers and clearing (Wise staff views only).
    settlement_detail: SettlementDetail | None = None


class StatementInvoice(ApiModel):
    invoice_id: UUID
    invoice_number: str
    version: int
    direction: Literal["PAYABLE", "RECEIVABLE"]
    outstanding: Money
    cancelled: Money
    residual: Money


class StatementCounterparty(ApiModel):
    name: str
    invoices: list[StatementInvoice]


class StatementFxLeg(ApiModel):
    from_amount: Money
    to_amount: Money
    rate: str  # decimal string, never a float


class StatementPricing(ApiModel):
    baseline: Money
    actual: Money
    net_benefit: Money
    standard_rate_bps: int
    fee_share_bps: int


class StatementInstruction(ApiModel):
    type: Literal["DEBIT", "CREDIT", "NONE"]
    counterparty: str
    amount: Money
    reference: str


class StatementApproval(ApiModel):
    required_approvers: int
    deadline: datetime
    approval_count: int
    can_approve: bool


class StatementView(ApiModel):
    """PRD "Statement payload". `content_hash` covers the economic fields only (not the IDs,
    attempt, reference or approval block), so it survives a recompute that changes nothing."""

    statement_id: UUID
    run_id: UUID
    attempt: int
    member_id: UUID
    summary: str
    counterparties: list[StatementCounterparty]
    gross_payable: Money
    gross_receivable: Money
    net: Money
    carried: Money
    fx_legs: list[StatementFxLeg]
    fee: Money
    savings: Money
    pricing: StatementPricing
    price_version: str
    rules_version: str
    instruction: StatementInstruction
    approval: StatementApproval
    # MC-APR-03: the caller may take its own invoices out while the run awaits approval.
    can_withdraw: bool
    content_hash: str
    run_status: str
    current: bool
    current_statement_id: UUID | None
    issued_at: datetime


class KillView(ApiModel):
    id: UUID
    scope: str
    member_id: UUID | None
    enabled: bool
    reason: str | None


class MemberRow(ApiModel):
    id: UUID
    name: str
    state: str
    funding_blocked: bool


class AdminOverview(ApiModel):
    members: list[MemberRow]
    runs: list[RunView]
    kill_switches: list[KillView]
