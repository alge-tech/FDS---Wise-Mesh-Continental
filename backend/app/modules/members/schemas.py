from uuid import UUID

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


class SettingsUpdate(StrictModel):
    payable_limit_minor: int | None = None
    maker_checker_minor: int | None = None
    settlement_currency: str | None = None


class TeamMember(ApiModel):
    user_id: UUID
    email: str
    display_name: str
    role: Role
