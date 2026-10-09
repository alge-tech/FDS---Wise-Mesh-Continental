"""MC-RSK-02 ring detection. Pure, no database."""

import random
from uuid import UUID, uuid5

from app.modules.risk.rules import RingInvoice, find_rings

NS = UUID("00000000-0000-0000-0000-0000000000a1")
UNIT = {"EUR": 100_000, "USD": 100_000}  # 1,000.00 in minor units


def m(code: str) -> UUID:
    return uuid5(NS, code)


def inv(n: str, payer: str, receiver: str, amount: int, currency: str = "EUR") -> RingInvoice:
    return RingInvoice(uuid5(NS, f"inv-{n}"), m(payer), m(receiver), currency, amount)


RECENT = {m(x) for x in "ABCDEF"}
RING = [inv("1", "A", "B", 500_000), inv("2", "B", "C", 500_000), inv("3", "C", "A", 500_000)]


def numbers(rings: list[tuple[RingInvoice, ...]]) -> list[set[UUID]]:
    return [{r.invoice_id for r in ring} for ring in rings]


def test_equal_round_cycle_between_new_members_is_a_ring() -> None:
    assert numbers(find_rings(RING, RECENT, UNIT)) == [{r.invoice_id for r in RING}]


def test_two_party_round_trip_counts_as_a_ring() -> None:
    pair = [inv("p", "A", "B", 200_000), inv("q", "B", "A", 200_000)]
    assert len(find_rings(pair, RECENT, UNIT)) == 1


def test_each_condition_is_required() -> None:
    unequal = [*RING[:2], inv("3", "C", "A", 400_000)]
    assert find_rings(unequal, RECENT, UNIT) == []
    off_unit = [RingInvoice(r.invoice_id, r.payer, r.receiver, r.currency, 500_010) for r in RING]
    assert find_rings(off_unit, RECENT, UNIT) == []
    assert find_rings(RING, RECENT - {m("B")}, UNIT) == []  # one established member
    assert find_rings([*RING[:2]], RECENT, UNIT) == []  # no cycle
    mixed = [*RING[:2], inv("3", "C", "A", 500_000, "USD")]
    assert find_rings(mixed, RECENT, UNIT) == []  # equal amounts, different currencies
    assert find_rings(RING, RECENT, {}) == []  # no unit for the currency


def test_parallel_invoices_form_separate_rings_and_extras_are_left_alone() -> None:
    doubled = [
        *RING,
        inv("4", "A", "B", 500_000),
        inv("5", "B", "C", 500_000),
        inv("6", "C", "A", 500_000),
        inv("7", "A", "B", 500_000),  # one A->B too many: it has no return leg
    ]
    rings = find_rings(doubled, RECENT, UNIT)
    assert len(rings) == 2
    flagged = set().union(*numbers(rings))
    assert len(flagged) == 6
    a_to_b = {inv(n, "A", "B", 0).invoice_id for n in "147"}
    assert len(a_to_b - flagged) == 1


def test_result_does_not_depend_on_input_order() -> None:
    data = [*RING, inv("x", "D", "E", 300_000), inv("y", "E", "D", 300_000)]
    expected = find_rings(data, RECENT, UNIT)
    for seed in range(5):
        shuffled = data[:]
        random.Random(seed).shuffle(shuffled)
        assert find_rings(shuffled, RECENT, UNIT) == expected
