from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.core.schemas import ApiModel, StrictModel
from app.modules.settlement.schemas import MemberSettlement, SettlementDetail


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
    content_hash: str = Field(min_length=64, max_length=64)
    reason_code: str | None = None


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


class StatementView(ApiModel):
    id: UUID
    run_id: UUID
    run_status: str
    current: bool
    current_statement_id: UUID | None
    content_hash: str
    content: dict[str, Any]
    required_approvers: int
    approval_count: int
    can_approve: bool
    issued_at: datetime
    expires_at: datetime


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
