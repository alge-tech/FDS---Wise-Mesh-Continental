from uuid import UUID

from pydantic import Field

from app.core.enums import MemberState, Role
from app.core.schemas import ApiModel, Money, StrictModel


class LoginRequest(StrictModel):
    email: str
    password: str


class MemberSummary(ApiModel):
    member_id: UUID
    name: str
    settlement_currency: str
    state: MemberState


class Me(ApiModel):
    user_id: UUID
    email: str
    display_name: str
    role: Role
    member: MemberSummary | None
    demo_mode: bool


class BalanceOut(ApiModel):
    currency: str
    available: Money
    held: Money


class TeamMember(ApiModel):
    user_id: UUID
    email: str
    display_name: str
    role: Role


class MemberDetail(ApiModel):
    member_id: UUID
    name: str
    legal_name: str
    state: MemberState
    risk_tier: str
    settlement_currency: str
    payable_limit: Money | None
    maker_checker_threshold: Money | None
    balances: list[BalanceOut]
    team: list[TeamMember]


class SettingsUpdate(StrictModel):
    """MC-ONB-02. Omit a field to keep it; send null to remove a limit or threshold.

    Amounts are minor units of the settlement currency in force after this change.
    """

    payable_limit_minor: int | None = Field(default=None, ge=0, le=10**15)
    maker_checker_minor: int | None = Field(default=None, ge=0, le=10**15)
    settlement_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    reason_code: str = Field(default="SETTINGS_UPDATED", min_length=1, max_length=200)
