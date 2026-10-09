"""Engine contract. Frozen dataclasses in, frozen dataclasses out; no database access."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Any
from uuid import UUID

from app.core.enums import PartyType

FX_PARTY = "FX"
CARRY_PARTY = "CARRY"

# Internal party key: str(member UUID) for members, or one of the pseudo-party names.
PartyKey = str


@dataclass(frozen=True)
class Edge:
    """One invoice: `payer` owes `receiver` (the issuer) `amount_minor` (outstanding, > 0)."""

    invoice_id: UUID
    payer: UUID
    receiver: UUID
    amount_minor: int
    currency: str


@dataclass(frozen=True)
class CarryIn:
    """A dust residual carried from an earlier run; positive means the member is owed it."""

    member: UUID
    currency: str
    amount_minor: int


def _frozen(mapping: Mapping[Any, Any] | None = None) -> Mapping[Any, Any]:
    return MappingProxyType(dict(mapping or {}))


@dataclass(frozen=True)
class EngineInput:
    edges: tuple[Edge, ...]
    rates: Mapping[tuple[str, str], Decimal]  # (base, quote) -> quote units per base unit
    settlement_currency: Mapping[UUID, str]
    payable_limit_minor: Mapping[UUID, int]  # member absent = no limit
    excluded_members: frozenset[UUID]
    time_budget_ms: int
    algo_version: str
    currency_exponents: Mapping[str, int] = field(default_factory=_frozen)
    dust_threshold_minor: int = 0
    carry_in: tuple[CarryIn, ...] = ()


@dataclass(frozen=True)
class NetPosition:
    """Settleable position in one currency (positive = receives).

    For a member whose residual is below the dust threshold, `amount_minor` is 0 and the
    residual sits in `carried_minor`; the CARRY pseudo-party holds the matching amount, so
    positions still sum to zero per currency. Members appear in their settlement currency
    (after the FX pass); the FX pseudo-party appears in every currency it converted.
    """

    party_type: PartyType
    member_id: UUID | None
    currency: str
    amount_minor: int
    carried_minor: int = 0
    gross_in_minor: int = 0
    gross_out_minor: int = 0

    @property
    def economic_minor(self) -> int:
        return self.amount_minor + self.carried_minor


@dataclass(frozen=True)
class PlannedTransfer:
    payer_type: PartyType
    payer_member_id: UUID | None
    receiver_type: PartyType
    receiver_member_id: UUID | None
    currency: str
    amount_minor: int
    kind: str  # SETTLEMENT or FX_LEG


@dataclass(frozen=True)
class Cancellation:
    invoice_id: UUID
    cycle_no: int
    amount_minor: int


@dataclass(frozen=True)
class InvoiceOutcome:
    invoice_id: UUID
    outstanding_minor: int
    cancelled_minor: int
    residual_minor: int
    outcome: str  # SETTLED_BY_NETTING or SETTLED_BY_TRANSFER


@dataclass(frozen=True)
class FxLeg:
    member_id: UUID
    from_currency: str
    from_amount_minor: int  # signed
    to_currency: str
    to_amount_minor: int  # signed
    rate: Decimal


@dataclass(frozen=True)
class Carry:
    member_id: UUID
    currency: str
    amount_minor: int  # signed


@dataclass(frozen=True)
class DroppedInvoice:
    invoice_id: UUID
    reason: str  # MEMBER_EXCLUDED, LIMIT_EXCEEDED or NO_RATE


@dataclass(frozen=True)
class Metrics:
    invoice_count: int
    member_count: int
    gross_minor: Mapping[str, int]
    cancelled_minor: Mapping[str, int]
    net_minor: Mapping[str, int]
    transfer_count: int
    greedy_transfer_count: int
    cycles_cancelled: int
    improved: bool
    fallback_to_greedy: bool
    limit_restarts: int
    dust_carried: int
    improvement_ops: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "invoice_count": self.invoice_count,
            "member_count": self.member_count,
            "gross_minor": dict(self.gross_minor),
            "cancelled_minor": dict(self.cancelled_minor),
            "net_minor": dict(self.net_minor),
            "transfer_count": self.transfer_count,
            "greedy_transfer_count": self.greedy_transfer_count,
            "cycles_cancelled": self.cycles_cancelled,
            "improved": self.improved,
            "fallback_to_greedy": self.fallback_to_greedy,
            "limit_restarts": self.limit_restarts,
            "dust_carried": self.dust_carried,
            "improvement_ops": self.improvement_ops,
        }


@dataclass(frozen=True)
class EngineResult:
    positions: tuple[NetPosition, ...]
    transfers: tuple[PlannedTransfer, ...]
    cancellations: tuple[Cancellation, ...]
    outcomes: tuple[InvoiceOutcome, ...]
    fx_legs: tuple[FxLeg, ...]
    carries: tuple[Carry, ...]  # new dust parked in SUSPENSE for the next window
    carry_in_used: tuple[Carry, ...]  # earlier dust paid out of SUSPENSE in this run
    dropped: tuple[DroppedInvoice, ...]
    limit_excluded: tuple[UUID, ...]
    metrics: Metrics
    input_hash: str
    result_hash: str
    seed: int


class EngineInvariantError(RuntimeError):
    """A money invariant failed; the computation must be discarded."""
