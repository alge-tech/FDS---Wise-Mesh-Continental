"""Property-based tests on random graphs (PRD test plan, "Property-based")."""

import random
from collections import defaultdict
from uuid import UUID

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.core.enums import LedgerAccountType, PartyType
from app.core.money import convert_minor
from app.modules.ledger.postings import build_commit_postings, plan_holds, sum_by_currency
from app.modules.netting.engine import run_netting
from app.modules.netting.fx_pass import lookup_rate
from app.modules.netting.matching import greedy
from app.modules.netting.types import CarryIn, Edge, EngineInput
from tests.engine_helpers import EXPONENTS, RATES, invoice, make_input, member

CURRENCIES = ["EUR", "USD", "GBP"]


@st.composite
def graphs(draw: st.DrawFn, multi_currency: bool = True) -> EngineInput:
    n_members = draw(st.integers(min_value=2, max_value=9))
    codes = [f"m{i}" for i in range(n_members)]
    n_edges = draw(st.integers(min_value=1, max_value=30))
    edges = []
    for i in range(n_edges):
        payer = draw(st.sampled_from(codes))
        receiver = draw(st.sampled_from([c for c in codes if c != payer]))
        currency = draw(st.sampled_from(CURRENCIES if multi_currency else ["EUR"]))
        amount = draw(st.integers(min_value=1, max_value=5_000_000))
        edges.append(Edge(invoice(f"e{i}"), member(payer), member(receiver), amount, currency))
    settlement = {
        member(c): draw(st.sampled_from(CURRENCIES if multi_currency else ["EUR"])) for c in codes
    }
    dust = draw(st.sampled_from([0, 100]))
    budget = draw(st.sampled_from([0, 5]))
    limits: dict[UUID, int] = {}
    if draw(st.booleans()):
        limited = draw(st.sampled_from(codes))
        limits[member(limited)] = draw(st.integers(min_value=0, max_value=3_000_000))
    return make_input(
        tuple(edges), settlement=settlement, limits=limits, dust=dust, budget_ms=budget
    )


@st.composite
def grouped_graphs(draw: st.DrawFn) -> EngineInput:
    """Disjoint zero-sum groups (one receiver, 1-3 payers) plus cycles over everything.

    Random amounts almost never form zero-sum subsets, so this is what exercises the
    improvement pass (MC-NET-05).
    """
    edges: list[Edge] = []
    codes: list[str] = []
    n_groups = draw(st.integers(min_value=2, max_value=5))
    for g in range(n_groups):
        receiver = f"g{g}r"
        payers = [f"g{g}p{i}" for i in range(draw(st.integers(min_value=1, max_value=3)))]
        codes += [receiver, *payers]
        for p in payers:
            amount = draw(st.integers(min_value=1, max_value=50)) * 1_000
            edges.append(
                Edge(invoice(f"{p}-{receiver}"), member(p), member(receiver), amount, "EUR")
            )
    for i in range(draw(st.integers(min_value=0, max_value=3))):
        ring = draw(st.lists(st.sampled_from(codes), min_size=3, max_size=5, unique=True))
        amount = draw(st.integers(min_value=1, max_value=20)) * 1_000
        for j, payer in enumerate(ring):
            receiver = ring[(j + 1) % len(ring)]
            edges.append(
                Edge(invoice(f"ring{i}-{j}"), member(payer), member(receiver), amount, "EUR")
            )
    return make_input(tuple(edges), budget_ms=20)


PROPS = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@PROPS
@given(grouped_graphs())
def test_grouped_graphs_improvement_is_valid_and_never_worse(inp: EngineInput) -> None:
    result = run_netting(inp)
    assert result.metrics.transfer_count <= result.metrics.greedy_transfer_count
    open_: dict[str, int] = defaultdict(int)
    for p in result.positions:
        open_[str(p.member_id)] += p.amount_minor
    for t in result.transfers:
        assert t.amount_minor > 0
        open_[str(t.payer_member_id)] += t.amount_minor
        open_[str(t.receiver_member_id)] -= t.amount_minor
    assert all(v == 0 for v in open_.values())
    edges = list(inp.edges)
    random.Random(3).shuffle(edges)
    again = run_netting(EngineInput(**{**inp.__dict__, "edges": tuple(edges)}))
    assert again.result_hash == result.result_hash


@PROPS
@given(graphs())
def test_positions_sum_to_zero_per_currency(inp: EngineInput) -> None:
    result = run_netting(inp)
    totals: dict[str, int] = defaultdict(int)
    for p in result.positions:
        totals[p.currency] += p.amount_minor
    assert all(v == 0 for v in totals.values()), totals


@PROPS
@given(graphs())
def test_plan_clears_every_position(inp: EngineInput) -> None:
    result = run_netting(inp)
    open_: dict[tuple[str, str, str], int] = defaultdict(int)
    for p in result.positions:
        open_[(p.currency, p.party_type, str(p.member_id))] += p.amount_minor
    for t in result.transfers:
        assert t.amount_minor > 0
        open_[(t.currency, t.payer_type, str(t.payer_member_id))] += t.amount_minor
        open_[(t.currency, t.receiver_type, str(t.receiver_member_id))] -= t.amount_minor
    assert all(v == 0 for v in open_.values())


@PROPS
@given(graphs())
def test_cancelled_plus_residual_equals_outstanding(inp: EngineInput) -> None:
    result = run_netting(inp)
    cancelled: dict[UUID, int] = defaultdict(int)
    for c in result.cancellations:
        assert c.amount_minor > 0
        cancelled[c.invoice_id] += c.amount_minor
    included = {o.invoice_id for o in result.outcomes}
    dropped = {d.invoice_id for d in result.dropped}
    assert included.isdisjoint(dropped)
    assert included | dropped == {e.invoice_id for e in inp.edges}
    for o in result.outcomes:
        assert o.cancelled_minor == cancelled.get(o.invoice_id, 0)
        assert o.cancelled_minor + o.residual_minor == o.outstanding_minor
        assert (o.residual_minor == 0) == (o.outcome == "SETTLED_BY_NETTING")


@PROPS
@given(graphs())
def test_improved_never_longer_than_greedy_and_within_k_minus_1(inp: EngineInput) -> None:
    result = run_netting(inp)
    assert result.metrics.transfer_count <= result.metrics.greedy_transfer_count
    by_currency: dict[str, int] = defaultdict(int)
    for p in result.positions:
        if p.amount_minor:
            by_currency[p.currency] += 1
    bound = sum(max(k - 1, 0) for k in by_currency.values())
    assert result.metrics.transfer_count <= bound


@PROPS
@given(graphs())
def test_same_input_same_hash_even_when_shuffled(inp: EngineInput) -> None:
    edges = list(inp.edges)
    random.Random(7).shuffle(edges)
    shuffled = EngineInput(**{**inp.__dict__, "edges": tuple(edges)})
    a, b = run_netting(inp), run_netting(shuffled)
    assert a.result_hash == b.result_hash
    assert a.input_hash == b.input_hash


@PROPS
@given(graphs())
def test_engine_positions_match_naive_reference(inp: EngineInput) -> None:
    """Reference: per member, convert each currency's naive net into the settlement currency."""
    result = run_netting(inp)
    excluded = set(inp.excluded_members) | set(result.limit_excluded)
    dropped = {d.invoice_id for d in result.dropped}
    naive: dict[tuple[UUID, str], int] = defaultdict(int)
    for e in inp.edges:
        if e.invoice_id in dropped or e.payer in excluded or e.receiver in excluded:
            continue
        naive[(e.receiver, e.currency)] += e.amount_minor
        naive[(e.payer, e.currency)] -= e.amount_minor
    expected: dict[UUID, int] = defaultdict(int)
    for (m, currency), amount in naive.items():
        target = inp.settlement_currency[m]
        if currency == target or not amount:
            expected[m] += amount  # a member whose currency nets to zero still has a position
        else:
            rate = lookup_rate(inp.rates, currency, target)
            expected[m] += convert_minor(amount, rate, EXPONENTS[currency], EXPONENTS[target])
    got = {
        p.member_id: p.economic_minor for p in result.positions if p.party_type == PartyType.MEMBER
    }
    assert got == {m: v for m, v in expected.items() if m in got}
    assert set(got) == {m for m, _ in naive}


@PROPS
@given(graphs())
def test_g2_settling_through_the_ledger_equals_paying_gross(inp: EngineInput) -> None:
    """G2: each member ends with its converted gross net, fees aside, and nothing else.

    Apply the commit postings (with zero fees) to empty wallets: each member's balance plus
    hold plus suspense must equal its economic net in its settlement currency, and be zero
    in every other currency. Every entry balances and the run's clearing ends at zero.
    """
    result = run_netting(inp)
    plans = plan_holds(result, {})
    lines = build_commit_postings(result, {})
    assert all(v == 0 for v in sum_by_currency(lines).values())

    wallet: dict[tuple[UUID | None, str, LedgerAccountType], int] = defaultdict(int)
    for plan in plans.values():  # prepare moved the hold out of the balance
        wallet[(plan.member_id, plan.currency, LedgerAccountType.MEMBER_BALANCE)] -= plan.hold_minor
        wallet[(plan.member_id, plan.currency, LedgerAccountType.MEMBER_HOLD)] += plan.hold_minor
    for line in lines:
        wallet[(line.account.member_id, line.account.currency, line.account.type)] += (
            line.amount_minor
        )

    clearing = {k: v for k, v in wallet.items() if k[2] == LedgerAccountType.CLEARING}
    assert all(v == 0 for v in clearing.values())
    holds = {k: v for k, v in wallet.items() if k[2] == LedgerAccountType.MEMBER_HOLD}
    assert all(v == 0 for v in holds.values())

    for p in result.positions:
        if p.party_type != PartyType.MEMBER:
            continue
        mine = sum(
            v
            for (m, c, t), v in wallet.items()
            if m == p.member_id
            and c == p.currency
            and t in (LedgerAccountType.MEMBER_BALANCE, LedgerAccountType.SUSPENSE)
        )
        assert mine == p.economic_minor
        others = sum(v for (m, c, _), v in wallet.items() if m == p.member_id and c != p.currency)
        assert others == 0


@PROPS
@given(graphs(multi_currency=False))
def test_fees_come_out_of_holds_and_receipts(inp: EngineInput) -> None:
    result = run_netting(inp)
    members = [p.member_id for p in result.positions if p.member_id is not None]
    fees = {m: 37 for m in members}
    lines = build_commit_postings(result, fees)
    assert all(v == 0 for v in sum_by_currency(lines).values())
    revenue = sum(
        line.amount_minor for line in lines if line.account.type == LedgerAccountType.FEE_REVENUE
    )
    assert revenue == 37 * len(members)


def test_carry_in_is_paid_out_of_suspense() -> None:
    a, b = member("a"), member("b")
    inp = make_input((Edge(invoice("c1"), a, b, 10_000, "EUR"),), dust=100)
    inp = EngineInput(**{**inp.__dict__, "carry_in": (CarryIn(a, "EUR", 40),)})
    result = run_netting(inp)
    assert [(c.member_id, c.amount_minor) for c in result.carry_in_used] == [(a, 40)]
    nets = {p.member_id: p.amount_minor for p in result.positions if p.member_id}
    assert nets == {a: -9_960, b: 10_000}
    lines = build_commit_postings(result, {})
    assert all(v == 0 for v in sum_by_currency(lines).values())


def test_greedy_matches_the_largest_pair_first() -> None:
    moves = greedy({"a": -50, "b": -30, "c": 60, "d": 20})
    assert (moves[0].payer, moves[0].receiver, moves[0].amount_minor) == ("a", "c", 50)
    assert len(moves) <= 3


def test_missing_rate_drops_the_cross_currency_invoice() -> None:
    a, b = member("a"), member("b")
    inp = make_input(
        (Edge(invoice("x1"), a, b, 10_000, "CNY"), Edge(invoice("x2"), b, a, 5_000, "EUR")),
        rates={k: v for k, v in RATES.items() if "CNY" not in k},
    )
    result = run_netting(inp)
    assert [(d.invoice_id, d.reason) for d in result.dropped] == [(invoice("x1"), "NO_RATE")]
