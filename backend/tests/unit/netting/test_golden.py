"""MC-NET-08 golden scenario, plus the PRD's two-pair case and the improvement example."""

from app.core.enums import InvoiceOutcomeKind, PartyType
from app.modules.demo.scenarios import IMPROVEMENT_EXAMPLE, WORKED_EXAMPLE
from app.modules.netting.engine import run_netting
from app.modules.netting.types import Edge
from tests.engine_helpers import edges_from, invoice, make_input, member

K = 100_000  # EUR 1,000 in minor units


def test_worked_example_gives_three_transfers_worth_80k() -> None:
    result = run_netting(make_input(edges_from(WORKED_EXAMPLE)))

    transfers = {
        (t.payer_member_id, t.receiver_member_id, t.amount_minor) for t in result.transfers
    }
    assert transfers == {
        (member("A"), member("F"), 40 * K),
        (member("C"), member("F"), 30 * K),
        (member("E"), member("F"), 10 * K),
    }
    assert sum(t.amount_minor for t in result.transfers) == 80 * K
    assert result.metrics.gross_minor == {"EUR": 450 * K}
    assert result.metrics.cancelled_minor == {"EUR": 270 * K}
    assert result.metrics.net_minor == {"EUR": 80 * K}
    assert result.metrics.cycles_cancelled == 2


def test_worked_example_positions() -> None:
    result = run_netting(make_input(edges_from(WORKED_EXAMPLE)))
    nets = {
        p.member_id: p.amount_minor for p in result.positions if p.party_type == PartyType.MEMBER
    }
    assert nets == {
        member("A"): -40 * K,
        member("B"): 0,
        member("C"): -30 * K,
        member("D"): 0,
        member("E"): -10 * K,
        member("F"): 80 * K,
    }


def test_worked_example_invoice_outcomes() -> None:
    result = run_netting(make_input(edges_from(WORKED_EXAMPLE)))
    by_number = {o.invoice_id: o for o in result.outcomes}

    netted = {invoice("WX-2026-003"), invoice("WX-2026-008")}  # C->A and F->D
    for inv_id, o in by_number.items():
        expected = (
            InvoiceOutcomeKind.SETTLED_BY_NETTING
            if inv_id in netted
            else InvoiceOutcomeKind.SETTLED_BY_TRANSFER
        )
        assert o.outcome == expected
    assert sum(o.residual_minor for o in result.outcomes) == 180 * K
    # The PRD's sample statement: A's invoice to B, 100k outstanding, 60k cancelled.
    a_to_b = by_number[invoice("WX-2026-001")]
    assert (a_to_b.outstanding_minor, a_to_b.cancelled_minor, a_to_b.residual_minor) == (
        100 * K,
        60 * K,
        40 * K,
    )


def test_two_independent_pairs_give_two_transfers() -> None:
    # Positions +30, -30, +50, -50.
    w, x, y, z = (member(c) for c in "WXYZ")
    edges = (
        Edge(invoice("p1"), w, x, 30 * K, "EUR"),
        Edge(invoice("p2"), y, z, 50 * K, "EUR"),
    )
    result = run_netting(make_input(edges))
    assert len(result.transfers) == 2


def test_improvement_example_beats_greedy() -> None:
    result = run_netting(make_input(edges_from(IMPROVEMENT_EXAMPLE), budget_ms=50))
    assert result.metrics.greedy_transfer_count == 5
    assert result.metrics.transfer_count == 4
    assert result.metrics.improved is True


def test_improvement_disabled_falls_back_to_greedy() -> None:
    result = run_netting(make_input(edges_from(IMPROVEMENT_EXAMPLE), budget_ms=0))
    assert result.metrics.transfer_count == 5
    assert result.metrics.improved is False


def test_same_input_same_hash() -> None:
    inp = make_input(edges_from(WORKED_EXAMPLE))
    assert run_netting(inp).result_hash == run_netting(inp).result_hash


def test_shuffled_input_same_hash() -> None:
    edges = edges_from(WORKED_EXAMPLE)
    a = run_netting(make_input(edges))
    b = run_netting(make_input(tuple(reversed(edges))))
    assert (a.input_hash, a.result_hash) == (b.input_hash, b.result_hash)
