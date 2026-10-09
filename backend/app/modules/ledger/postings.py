"""Pure posting builders for settlement. The ledger service resolves account refs to rows.

Every party (member, FX, CARRY) settles the same way through the run's clearing account:
it posts -p to CLEARING and +p to its own funding account. Clearing therefore nets to zero
exactly when positions sum to zero per currency (G1). Fees come out of the payer's hold,
or out of the receipt for a receiver, and go to FEE_REVENUE.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.core.enums import LedgerAccountType, PartyType
from app.modules.netting.types import Carry, NetPosition


class Settleable(Protocol):
    """What settlement needs from a computation: an EngineResult, or a plan rebuilt from rows."""

    @property
    def positions(self) -> Sequence[NetPosition]: ...

    @property
    def carries(self) -> Sequence[Carry]: ...

    @property
    def carry_in_used(self) -> Sequence[Carry]: ...


@dataclass(frozen=True)
class AccountRef:
    type: LedgerAccountType
    member_id: UUID | None
    currency: str
    run_scoped: bool = False  # CLEARING and MEMBER_HOLD are per run


@dataclass(frozen=True)
class PostingLine:
    account: AccountRef
    amount_minor: int  # signed


@dataclass(frozen=True)
class HoldPlan:
    member_id: UUID
    currency: str
    hold_minor: int  # net payable + the part of the fee not taken from a receipt
    fee_from_receipt_minor: int
    fee_from_hold_minor: int


def plan_holds(result: Settleable, fees: Mapping[UUID, int]) -> dict[UUID, HoldPlan]:
    plans: dict[UUID, HoldPlan] = {}
    for p in result.positions:
        if p.party_type != PartyType.MEMBER or p.member_id is None:
            continue
        fee = fees.get(p.member_id, 0)
        fee_from_receipt = min(fee, max(p.amount_minor, 0))
        fee_from_hold = fee - fee_from_receipt
        plans[p.member_id] = HoldPlan(
            member_id=p.member_id,
            currency=p.currency,
            hold_minor=max(-p.amount_minor, 0) + fee_from_hold,
            fee_from_receipt_minor=fee_from_receipt,
            fee_from_hold_minor=fee_from_hold,
        )
    return plans


def hold_postings(plan: HoldPlan) -> list[PostingLine]:
    """Prepare: move the hold amount from the member's balance into its run hold."""
    if plan.hold_minor == 0:
        return []
    return [
        PostingLine(
            AccountRef(LedgerAccountType.MEMBER_BALANCE, plan.member_id, plan.currency),
            -plan.hold_minor,
        ),
        PostingLine(
            AccountRef(LedgerAccountType.MEMBER_HOLD, plan.member_id, plan.currency, True),
            plan.hold_minor,
        ),
    ]


def release_postings(member_id: UUID, currency: str, amount_minor: int) -> list[PostingLine]:
    """Abort: return an active hold to the member's balance."""
    return [
        PostingLine(
            AccountRef(LedgerAccountType.MEMBER_HOLD, member_id, currency, True), -amount_minor
        ),
        PostingLine(
            AccountRef(LedgerAccountType.MEMBER_BALANCE, member_id, currency), amount_minor
        ),
    ]


def build_commit_postings(result: Settleable, fees: Mapping[UUID, int]) -> list[PostingLine]:
    """All postings of the single commit journal entry."""
    lines: list[PostingLine] = []

    def clearing(currency: str) -> AccountRef:
        return AccountRef(LedgerAccountType.CLEARING, None, currency, True)

    for p in result.positions:
        if p.party_type == PartyType.MEMBER and p.member_id is not None:
            if p.amount_minor == 0:
                continue
            funding_type = (
                LedgerAccountType.MEMBER_HOLD
                if p.amount_minor < 0
                else LedgerAccountType.MEMBER_BALANCE
            )
            funding = AccountRef(
                funding_type, p.member_id, p.currency, funding_type == LedgerAccountType.MEMBER_HOLD
            )
            lines += [
                PostingLine(clearing(p.currency), -p.amount_minor),
                PostingLine(funding, p.amount_minor),
            ]
        elif p.party_type == PartyType.FX:
            lines += [
                PostingLine(clearing(p.currency), -p.amount_minor),
                PostingLine(
                    AccountRef(LedgerAccountType.FX_CONVERSION, None, p.currency), p.amount_minor
                ),
            ]

    # The CARRY party's position is new dust minus carry-in paid out; book it per member.
    for c in result.carries:
        lines += [
            PostingLine(clearing(c.currency), -c.amount_minor),
            PostingLine(
                AccountRef(LedgerAccountType.SUSPENSE, c.member_id, c.currency), c.amount_minor
            ),
        ]
    for c in result.carry_in_used:
        lines += [
            PostingLine(clearing(c.currency), c.amount_minor),
            PostingLine(
                AccountRef(LedgerAccountType.SUSPENSE, c.member_id, c.currency), -c.amount_minor
            ),
        ]

    for plan in plan_holds(result, fees).values():
        fee = plan.fee_from_receipt_minor + plan.fee_from_hold_minor
        if fee == 0:
            continue
        if plan.fee_from_hold_minor:
            lines.append(
                PostingLine(
                    AccountRef(LedgerAccountType.MEMBER_HOLD, plan.member_id, plan.currency, True),
                    -plan.fee_from_hold_minor,
                )
            )
        if plan.fee_from_receipt_minor:
            lines.append(
                PostingLine(
                    AccountRef(LedgerAccountType.MEMBER_BALANCE, plan.member_id, plan.currency),
                    -plan.fee_from_receipt_minor,
                )
            )
        lines.append(
            PostingLine(AccountRef(LedgerAccountType.FEE_REVENUE, None, plan.currency), fee)
        )
    return [line for line in lines if line.amount_minor != 0]


def sum_by_currency(lines: Iterable[PostingLine]) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for line in lines:
        totals[line.account.currency] += line.amount_minor
    return dict(totals)
