"""MC-NET-01: components net on their own, and a failing one doesn't block the others."""

from typing import Any

import pytest

from app.modules.demo.scenarios import WORKED_EXAMPLE
from app.modules.netting import engine
from app.modules.netting.engine import run_netting
from app.modules.netting.matching import Move
from app.modules.netting.types import Edge, EngineInvariantError, PartyType
from app.modules.netting.validate import check_plan_clears
from tests.engine_helpers import edges_from, invoice, make_input, member

# Two disjoint loops: X -> Y -> Z -> X (EUR) and P <-> Q (EUR).
LOOP = (
    Edge(invoice("L1"), member("X"), member("Y"), 10_000, "EUR"),
    Edge(invoice("L2"), member("Y"), member("Z"), 7_000, "EUR"),
    Edge(invoice("L3"), member("Z"), member("X"), 4_000, "EUR"),
)
PAIR = (
    Edge(invoice("P1"), member("P"), member("Q"), 5_000, "EUR"),
    Edge(invoice("P2"), member("Q"), member("P"), 2_000, "EUR"),
)


def outcome_rows(result: Any) -> list[tuple[Any, ...]]:
    return sorted(
        (str(o.invoice_id), o.cancelled_minor, o.residual_minor, o.outcome) for o in result.outcomes
    )


def member_positions(result: Any) -> dict[Any, int]:
    return {
        p.member_id: p.amount_minor for p in result.positions if p.party_type == PartyType.MEMBER
    }


def test_components_are_found_and_ordered_by_smallest_member() -> None:
    edges = engine._eligible_edges(make_input(LOOP + PAIR), set())[0]
    parts = engine._components(edges)
    assert sorted(len(p) for p in parts) == [2, 3]
    smallest = [min((m for e in p for m in (e.payer, e.receiver)), key=str) for p in parts]
    assert smallest == sorted(smallest, key=str)


def test_netting_the_union_equals_netting_each_component() -> None:
    union = run_netting(make_input(LOOP + PAIR))
    alone = [run_netting(make_input(LOOP)), run_netting(make_input(PAIR))]
    assert union.metrics.component_count == 2 and union.metrics.failed_components == 0
    assert outcome_rows(union) == sorted(r for a in alone for r in outcome_rows(a))
    assert member_positions(union) == {**member_positions(alone[0]), **member_positions(alone[1])}
    assert union.metrics.cycles_cancelled == sum(a.metrics.cycles_cancelled for a in alone)
    assert len({c.cycle_no for c in union.cancellations}) == union.metrics.cycles_cancelled


def test_worked_example_is_one_component() -> None:
    result = run_netting(make_input(edges_from(WORKED_EXAMPLE)))
    assert (result.metrics.component_count, result.metrics.failed_components) == (1, 0)
    assert result.component_errors == ()


def test_a_failing_component_is_dropped_and_the_rest_still_nets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = engine.cancel_cycles
    bad = invoice("P1")

    def flaky(edges: tuple[Edge, ...]) -> Any:
        if any(e.invoice_id == bad for e in edges):
            raise EngineInvariantError("MC-NET-02: injected failure")
        return real(edges)

    monkeypatch.setattr(engine, "cancel_cycles", flaky)
    result = run_netting(make_input(LOOP + PAIR))

    assert result.metrics.component_count == 2 and result.metrics.failed_components == 1
    assert result.component_errors == ("MC-NET-02: injected failure",)
    assert {d.invoice_id: d.reason for d in result.dropped} == {
        invoice("P1"): "COMPONENT_FAILED",
        invoice("P2"): "COMPONENT_FAILED",
    }
    assert outcome_rows(result) == outcome_rows(run_netting(make_input(LOOP)))
    assert set(member_positions(result)) == {member("X"), member("Y"), member("Z")}
    assert result.metrics.invoice_count == 3
    positions = {str(p.member_id): p.amount_minor for p in result.positions if p.amount_minor}
    check_plan_clears(
        "EUR",
        positions,
        [
            Move(str(t.payer_member_id), str(t.receiver_member_id), t.amount_minor)
            for t in result.transfers
        ],
    )


def test_every_component_failing_leaves_nothing_to_net(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(edges: tuple[Edge, ...]) -> Any:
        raise EngineInvariantError("boom")

    monkeypatch.setattr(engine, "cancel_cycles", broken)
    result = run_netting(make_input(LOOP + PAIR))
    assert result.outcomes == () and result.transfers == ()
    assert result.component_errors == ("boom", "boom")
    assert len(result.dropped) == 5


def test_malformed_input_still_fails_the_whole_run() -> None:
    bad = (Edge(invoice("S"), member("X"), member("X"), 1, "EUR"),)
    with pytest.raises(EngineInvariantError, match="same payer and receiver"):
        run_netting(make_input(LOOP + bad))
