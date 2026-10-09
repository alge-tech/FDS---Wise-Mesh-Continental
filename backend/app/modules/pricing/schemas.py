from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.core.schemas import ApiModel, Money, StrictModel


class SavingsItem(ApiModel):
    """One run, in the member's settlement currency. `savings` is baseline minus actual."""

    run_id: UUID
    status: str
    settled: bool
    settled_at: datetime | None
    currency: str
    gross_payable: Money
    net_paid: Money
    net_received: Money
    baseline: Money
    actual: Money
    fee: Money
    savings: Money
    price_version: str


class SavingsTotal(ApiModel):
    currency: str
    runs: int
    gross_payable: Money
    net_paid: Money
    baseline: Money
    actual: Money
    fee: Money
    savings: Money


class SavingsSummary(ApiModel):
    items: list[SavingsItem]
    totals: list[SavingsTotal]  # settled runs only


class EstimateRequest(StrictModel):
    """Break-even calculator (MC-FEE-03). Uses a run's figures, or amounts typed in."""

    standard_rate_bps: int = Field(ge=0, le=1000)
    fee_share_bps: int = Field(ge=0, le=10_000)
    run_id: str | None = None
    gross_payable_minor: int | None = Field(default=None, ge=0, le=10**15)
    net_payable_minor: int | None = Field(default=None, ge=0, le=10**15)

    @model_validator(mode="after")
    def one_source(self) -> "EstimateRequest":
        typed = (self.gross_payable_minor, self.net_payable_minor)
        if self.run_id is not None:
            UUID(self.run_id)
            if any(v is not None for v in typed):
                raise ValueError("Send a run ID or amounts, not both.")
        elif None in typed:
            raise ValueError("Send a run ID, or both gross and net payable amounts.")
        elif self.net_payable_minor > self.gross_payable_minor:  # type: ignore[operator]
            raise ValueError("Net payable can't exceed gross payable.")
        return self


class Estimate(ApiModel):
    source: Literal["RUN", "INPUT"]
    run_id: UUID | None
    currency: str
    standard_rate_bps: int
    fee_share_bps: int
    gross_payable: Money
    net_payable: Money
    baseline: Money  # gross payables x standard rate
    actual: Money  # net payable x standard rate + Mesh fee
    fee: Money
    gross_savings: Money  # before the Mesh fee
    savings: Money  # what the member keeps: baseline - actual
    break_even_fee_share_bps: int | None  # fee share at which Mesh costs as much as gross
