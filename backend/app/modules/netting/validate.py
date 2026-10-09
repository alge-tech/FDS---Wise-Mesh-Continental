"""MC-NET-06 checks. Any failure raises EngineInvariantError."""

from collections import defaultdict
from collections.abc import Iterable

from app.modules.netting.matching import Move
from app.modules.netting.types import (
    Cancellation,
    Edge,
    EngineInvariantError,
    InvoiceOutcome,
    PartyKey,
)


def check_zero_sum(positions: dict[str, dict[PartyKey, int]]) -> None:
    for currency, parties in positions.items():
        total = sum(parties.values())
        if total != 0:
            raise EngineInvariantError(f"G1: positions in {currency} sum to {total}, not 0")


def check_plan_clears(currency: str, positions: dict[PartyKey, int], moves: Iterable[Move]) -> None:
    after = dict(positions)
    for m in moves:
        if m.amount_minor <= 0:
            raise EngineInvariantError(f"non-positive transfer in {currency}")
        if m.payer == m.receiver:
            raise EngineInvariantError(f"self-transfer in {currency}")
        after[m.payer] = after.get(m.payer, 0) + m.amount_minor
        after[m.receiver] = after.get(m.receiver, 0) - m.amount_minor
    leftover = {k: v for k, v in after.items() if v != 0}
    if leftover:
        raise EngineInvariantError(f"plan leaves {len(leftover)} positions open in {currency}")


def check_outcomes(
    edges: tuple[Edge, ...],
    cancellations: Iterable[Cancellation],
    outcomes: Iterable[InvoiceOutcome],
) -> None:
    cancelled: dict[object, int] = defaultdict(int)
    for c in cancellations:
        if c.amount_minor <= 0:
            raise EngineInvariantError("non-positive cancellation")
        cancelled[c.invoice_id] += c.amount_minor
    by_invoice = {o.invoice_id: o for o in outcomes}
    if len(by_invoice) != len(edges) or {e.invoice_id for e in edges} != set(by_invoice):
        raise EngineInvariantError("G6: every included invoice needs exactly one outcome")
    for e in edges:
        o = by_invoice[e.invoice_id]
        if o.outstanding_minor != e.amount_minor:
            raise EngineInvariantError("G6: outcome outstanding differs from the invoice")
        if o.cancelled_minor != cancelled.get(e.invoice_id, 0):
            raise EngineInvariantError("MC-NET-02: cancellations don't sum to cancelled")
        if o.residual_minor < 0 or o.cancelled_minor + o.residual_minor != o.outstanding_minor:
            raise EngineInvariantError("G6: cancelled + residual != outstanding")
