"""MC-NET-06: the validators catch broken plans. The property tests only see valid ones."""

from uuid import uuid4

import pytest

from app.modules.netting.matching import Move, greedy, improved
from app.modules.netting.types import Cancellation, Edge, EngineInvariantError, InvoiceOutcome
from app.modules.netting.validate import check_outcomes, check_plan_clears, check_zero_sum

POSITIONS = {"A": -40, "C": -30, "E": -10, "F": 80}


def test_zero_sum_passes_and_fails_per_currency() -> None:
    check_zero_sum({"EUR": POSITIONS, "USD": {"A": 5, "B": -5}})
    with pytest.raises(EngineInvariantError, match="G1: positions in USD sum to 1"):
        check_zero_sum({"EUR": POSITIONS, "USD": {"A": 6, "B": -5}})


@pytest.mark.parametrize("plan", [greedy(POSITIONS), improved(POSITIONS, 50)[0]])
def test_engine_plans_clear_every_position(plan: list[Move]) -> None:
    check_plan_clears("EUR", POSITIONS, plan)
    assert len(plan) == 3


@pytest.mark.parametrize(
    ("moves", "message"),
    [
        ([Move("A", "F", 40), Move("C", "F", 30)], "leaves 2 positions open"),
        ([Move("A", "F", 40), Move("C", "F", 30), Move("E", "F", 0)], "non-positive"),
        ([Move("A", "A", 5)], "self-transfer"),
        (
            [Move("A", "F", 40), Move("C", "F", 30), Move("E", "F", 10), Move("A", "F", 1)],
            "leaves 2 positions open",
        ),
    ],
)
def test_broken_plans_are_rejected(moves: list[Move], message: str) -> None:
    with pytest.raises(EngineInvariantError, match=message):
        check_plan_clears("EUR", POSITIONS, moves)


def _edge(amount: int) -> Edge:
    return Edge(uuid4(), uuid4(), uuid4(), amount, "EUR")


def test_consistent_outcomes_pass() -> None:
    e1, e2 = _edge(100), _edge(60)
    check_outcomes(
        (e1, e2),
        [Cancellation(e1.invoice_id, 1, 60), Cancellation(e2.invoice_id, 1, 60)],
        [
            InvoiceOutcome(e1.invoice_id, 100, 60, 40, "SETTLED_BY_TRANSFER"),
            InvoiceOutcome(e2.invoice_id, 60, 60, 0, "SETTLED_BY_NETTING"),
        ],
    )


def test_outcome_checks_catch_each_kind_of_break() -> None:
    e = _edge(100)
    ok = InvoiceOutcome(e.invoice_id, 100, 60, 40, "SETTLED_BY_TRANSFER")
    cancel = [Cancellation(e.invoice_id, 1, 60)]

    with pytest.raises(EngineInvariantError, match="exactly one outcome"):
        check_outcomes((e,), cancel, [])
    with pytest.raises(EngineInvariantError, match="exactly one outcome"):
        check_outcomes((e,), cancel, [ok, InvoiceOutcome(uuid4(), 1, 0, 1, "X")])
    with pytest.raises(EngineInvariantError, match="outstanding differs"):
        check_outcomes((e,), cancel, [InvoiceOutcome(e.invoice_id, 99, 60, 39, "X")])
    with pytest.raises(EngineInvariantError, match="don't sum to cancelled"):
        check_outcomes((e,), [Cancellation(e.invoice_id, 1, 50)], [ok])
    with pytest.raises(EngineInvariantError, match="cancelled \\+ residual"):
        check_outcomes((e,), cancel, [InvoiceOutcome(e.invoice_id, 100, 60, 30, "X")])
    with pytest.raises(EngineInvariantError, match="non-positive cancellation"):
        check_outcomes((e,), [Cancellation(e.invoice_id, 1, 0)], [ok])
