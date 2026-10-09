"""Gain-share pricing (MC-FEE-01, MC-FEE-02). Pure: shared by runs, statements and estimates.

Paying an invoice gross costs the payer the standard transfer rate on its amount. With
netting the member only moves its net payable. Per member, in its settlement currency:

  baseline = gross payables x standard rate
  savings  = baseline - net payable x standard rate      (never negative)
  fee      = its share of floor(sum of savings x fee share), split by savings with
             largest-remainder rounding, so fees sum to the total and fee <= savings
  actual   = net payable x standard rate + fee
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from app.core.money import allocate_largest_remainder, apply_bps, round_half_even


@dataclass(frozen=True)
class MemberPricingInput:
    member_id: UUID
    currency: str  # settlement currency
    gross_payable_minor: int
    net_payable_minor: int  # >= 0


@dataclass(frozen=True)
class FeeLine:
    member_id: UUID
    currency: str
    baseline_minor: int
    actual_minor: int
    savings_minor: int
    fee_minor: int

    @property
    def net_benefit_minor(self) -> int:
        """What the member keeps: baseline cost minus everything it pays with Mesh."""
        return self.baseline_minor - self.actual_minor


def compute_fees(
    members: Iterable[MemberPricingInput], standard_rate_bps: int, fee_share_bps: int
) -> dict[UUID, FeeLine]:
    if not 0 <= fee_share_bps <= 10_000:
        raise ValueError("fee share must be between 0 and 10000 bps")
    rows = sorted(members, key=lambda m: str(m.member_id))
    baseline: dict[UUID, int] = {}
    residual_cost: dict[UUID, int] = {}
    savings: dict[UUID, int] = {}
    groups: dict[str, list[UUID]] = defaultdict(list)
    for m in rows:
        if m.net_payable_minor < 0 or m.gross_payable_minor < 0:
            raise ValueError("payables must be non-negative")
        baseline[m.member_id] = round_half_even(apply_bps(m.gross_payable_minor, standard_rate_bps))
        residual_cost[m.member_id] = round_half_even(
            apply_bps(m.net_payable_minor, standard_rate_bps)
        )
        savings[m.member_id] = max(0, baseline[m.member_id] - residual_cost[m.member_id])
        groups[m.currency].append(m.member_id)

    fees: dict[UUID, int] = {}
    for _, ids in sorted(groups.items()):
        total_savings = sum(savings[i] for i in ids)
        total_fee = total_savings * fee_share_bps // 10_000
        fees.update(allocate_largest_remainder(total_fee, {i: savings[i] for i in ids}, ids))

    return {
        m.member_id: FeeLine(
            member_id=m.member_id,
            currency=m.currency,
            baseline_minor=baseline[m.member_id],
            actual_minor=residual_cost[m.member_id] + fees[m.member_id],
            savings_minor=savings[m.member_id],
            fee_minor=fees[m.member_id],
        )
        for m in rows
    }
