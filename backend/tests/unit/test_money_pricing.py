import ast
import pathlib
from decimal import Decimal
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.hashing import canonical_json, hash_canonical
from app.core.money import (
    MoneyParseError,
    allocate_largest_remainder,
    convert_minor,
    format_minor,
    parse_minor,
    round_half_even,
)
from app.modules.demo.scenarios import WORKED_EXAMPLE
from app.modules.netting.engine import run_netting
from app.modules.pricing.calc import MemberPricingInput, compute_fees
from tests.engine_helpers import edges_from, make_input, member

# --- money ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "exponent", "expected"),
    [
        ("1234.50", 2, 123450),
        ("1234", 2, 123400),
        ("0.07", 2, 7),
        ("15", 0, 15),
        ("1.234", 3, 1234),
        ("100000", 2, 10_000_000),
        ("  42.1 ", 2, 4210),
    ],
)
def test_parse_minor(text: str, exponent: int, expected: int) -> None:
    assert parse_minor(text, exponent) == expected


@pytest.mark.parametrize("text", ["1e3", "1,000.00", "-5", "12.345", "abc", "", "1.2.3", "+4"])
def test_parse_minor_rejects(text: str) -> None:
    with pytest.raises(MoneyParseError):
        parse_minor(text, 2)


@given(st.integers(min_value=-(10**15), max_value=10**15), st.sampled_from([0, 2, 3]))
def test_format_then_parse_round_trips(amount: int, exponent: int) -> None:
    assert parse_minor(format_minor(amount, exponent), exponent, allow_negative=True) == amount


def test_half_even() -> None:
    assert round_half_even(Decimal("2.5")) == 2
    assert round_half_even(Decimal("3.5")) == 4
    assert round_half_even(Decimal("-2.5")) == -2
    assert convert_minor(1000, Decimal("0.0025"), 2, 2) == 2  # 2.5 -> 2


@given(
    st.integers(min_value=0, max_value=10**9),
    st.lists(st.integers(min_value=0, max_value=10**9), min_size=1, max_size=20),
)
def test_largest_remainder_sums_exactly(total: int, weights: list[int]) -> None:
    if sum(weights) == 0:
        total = 0
    parts = allocate_largest_remainder(total, dict(enumerate(weights)))
    assert sum(parts.values()) == total
    assert all(p >= 0 for p in parts.values())


def test_canonical_json_is_sorted_and_rejects_floats() -> None:
    assert canonical_json({"b": 1, "a": [Decimal("0.10"), UUID(int=1)]}) == (
        '{"a":["0.10","00000000-0000-0000-0000-000000000001"],"b":1}'
    )
    with pytest.raises(TypeError):
        canonical_json({"x": 1.5})
    assert hash_canonical({"a": 1}) == hash_canonical({"a": 1})


# --- pricing --------------------------------------------------------------------------


def _worked_fees() -> dict[UUID, tuple[int, int, int, int]]:
    result = run_netting(make_input(edges_from(WORKED_EXAMPLE)))
    rows = [
        MemberPricingInput(p.member_id, p.currency, p.gross_out_minor, max(-p.economic_minor, 0))
        for p in result.positions
        if p.member_id is not None
    ]
    lines = compute_fees(rows, standard_rate_bps=52, fee_share_bps=2500)
    return {
        m: (f.baseline_minor, f.savings_minor, f.fee_minor, f.actual_minor)
        for m, f in lines.items()
    }


def test_worked_example_gain_share() -> None:
    fees = _worked_fees()
    eur = 100  # minor units per EUR
    # baseline = payables x 0.52%; savings = baseline - net payable x 0.52%; fee = 25%.
    assert fees[member("A")] == (520 * eur, 312 * eur, 78 * eur, (208 + 78) * eur)
    assert fees[member("B")] == (520 * eur, 520 * eur, 130 * eur, 130 * eur)
    assert fees[member("C")] == (572 * eur, 416 * eur, 104 * eur, (156 + 104) * eur)
    assert fees[member("D")] == (260 * eur, 260 * eur, 65 * eur, 65 * eur)
    assert fees[member("E")] == (312 * eur, 260 * eur, 65 * eur, (52 + 65) * eur)
    assert fees[member("F")] == (156 * eur, 156 * eur, 39 * eur, 39 * eur)
    assert sum(f[0] for f in fees.values()) == 2340 * eur  # 450k x 0.52%
    assert sum(f[2] for f in fees.values()) == 481 * eur  # 25% of 1,924 savings


@given(
    st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=10**10), st.integers(min_value=0, max_value=100)
        ),
        min_size=1,
        max_size=15,
    ),
    st.integers(min_value=0, max_value=10_000),
    st.integers(min_value=0, max_value=10_000),
)
def test_fee_never_exceeds_savings_and_sums_to_total(
    rows: list[tuple[int, int]], rate_bps: int, share_bps: int
) -> None:
    inputs = [
        MemberPricingInput(UUID(int=i + 1), "EUR", gross, gross * pct // 100)
        for i, (gross, pct) in enumerate(rows)
    ]
    lines = compute_fees(inputs, rate_bps, share_bps)
    total_savings = sum(f.savings_minor for f in lines.values())
    assert sum(f.fee_minor for f in lines.values()) == total_savings * share_bps // 10_000
    for f in lines.values():
        assert 0 <= f.fee_minor <= f.savings_minor


# --- layering -------------------------------------------------------------------------


def test_engine_imports_nothing_from_the_database_layer() -> None:
    root = pathlib.Path(__file__).resolve().parents[2] / "app" / "modules" / "netting"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                names = (
                    [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else [a.name for a in node.names]
                )
                for name in names:
                    assert not name.startswith("sqlalchemy"), path.name
                    assert name != "app.core.db", path.name


def test_money_code_never_uses_float() -> None:
    root = pathlib.Path(__file__).resolve().parents[2] / "app"
    for rel in [
        "core/money.py",
        "modules/netting",
        "modules/pricing/calc.py",
        "modules/ledger/postings.py",
    ]:
        target = root / rel
        files = [target] if target.is_file() else list(target.glob("*.py"))
        for path in files:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == "float":
                    raise AssertionError(f"float used in {path}")
                if isinstance(node, ast.Constant) and isinstance(node.value, float):
                    raise AssertionError(f"float literal in {path}")
