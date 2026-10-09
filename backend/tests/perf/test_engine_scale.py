"""Non-functional target: 1,000 members and 20,000 invoices in under 10 s on a laptop."""

import random
import time

import pytest

from app.modules.netting.engine import run_netting
from app.modules.netting.types import Edge
from tests.engine_helpers import invoice, make_input, member


@pytest.mark.slow
def test_engine_scale() -> None:
    rng = random.Random(2026)
    members = [member(f"p{i}") for i in range(1_000)]
    currencies = ["EUR", "EUR", "EUR", "USD", "GBP"]
    edges = []
    for i in range(20_000):
        payer, receiver = rng.sample(members, 2)
        edges.append(
            Edge(
                invoice(f"perf{i}"),
                payer,
                receiver,
                rng.randint(100, 5_000_000),
                rng.choice(currencies),
            )
        )
    settlement = {m: rng.choice(["EUR", "USD", "GBP"]) for m in members}
    inp = make_input(tuple(edges), settlement=settlement, budget_ms=2_000, dust=100)
    started = time.perf_counter()
    result = run_netting(inp)
    elapsed = time.perf_counter() - started
    print(
        f"\nengine: {len(edges)} invoices, {len(members)} members, "
        f"{result.metrics.transfer_count} transfers, {elapsed:.2f}s"
    )
    assert elapsed < 10
