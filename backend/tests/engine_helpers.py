"""Builders shared by the engine tests."""

from decimal import Decimal
from uuid import UUID, uuid5

from app.modules.demo.scenarios import ScenarioInvoice
from app.modules.netting.types import Edge, EngineInput

NS = UUID("00000000-0000-0000-0000-00000000a5e5")
EXPONENTS = {"EUR": 2, "USD": 2, "GBP": 2, "HUF": 2, "CNY": 2}
RATES = {
    ("EUR", "USD"): Decimal("1.0850000000"),
    ("EUR", "GBP"): Decimal("0.8450000000"),
    ("EUR", "HUF"): Decimal("395.1000000000"),
    ("EUR", "CNY"): Decimal("7.7800000000"),
    ("USD", "GBP"): Decimal("0.7790000000"),
}


def member(code: str) -> UUID:
    return uuid5(NS, f"member-{code}")


def invoice(number: str) -> UUID:
    return uuid5(NS, f"invoice-{number}")


def edges_from(scenario: tuple[ScenarioInvoice, ...]) -> tuple[Edge, ...]:
    return tuple(
        Edge(
            invoice(i.invoice_number),
            member(i.payer),
            member(i.issuer),
            i.amount_major * 100,
            i.currency,
        )
        for i in scenario
    )


def make_input(
    edges: tuple[Edge, ...],
    *,
    settlement: dict[UUID, str] | None = None,
    limits: dict[UUID, int] | None = None,
    excluded: frozenset[UUID] = frozenset(),
    budget_ms: int = 50,
    dust: int = 0,
    rates: dict[tuple[str, str], Decimal] | None = None,
) -> EngineInput:
    members = {e.payer for e in edges} | {e.receiver for e in edges}
    return EngineInput(
        edges=edges,
        rates=RATES if rates is None else rates,
        settlement_currency={m: (settlement or {}).get(m, "EUR") for m in members},
        payable_limit_minor=limits or {},
        excluded_members=excluded,
        time_budget_ms=budget_ms,
        algo_version="net-test",
        currency_exponents=EXPONENTS,
        dust_threshold_minor=dust,
    )
