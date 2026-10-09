"""Transfer planning per currency (MC-NET-04, MC-NET-05).

Greedy pairs the largest payer with the largest receiver until every position is zero,
which needs at most k - 1 transfers for k non-zero parties. The improvement pass first
settles disjoint zero-sum groups (exact pairs, then subsets of 3 or 4 parties) on their
own: a group of g parties needs only g - 1 transfers, so every group found saves one
transfer. Its budget counts operations rather than wall-clock time, so the same input
always gives the same plan.
"""

import heapq
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations

from app.modules.netting.types import PartyKey

# One operation is roughly one candidate examined. 1 ms of budget ~ 1,000 operations.
OPS_PER_MS = 1_000


@dataclass(frozen=True)
class Move:
    payer: PartyKey
    receiver: PartyKey
    amount_minor: int


def greedy(positions: dict[PartyKey, int]) -> list[Move]:
    """Largest payer pays largest receiver; ties broken by party key."""
    payers = [(p, k) for k, p in positions.items() if p < 0]  # p negative: most negative first
    receivers = [(-p, k) for k, p in positions.items() if p > 0]
    heapq.heapify(payers)
    heapq.heapify(receivers)
    moves: list[Move] = []
    while payers and receivers:
        neg_pay, payer = heapq.heappop(payers)
        neg_rec, receiver = heapq.heappop(receivers)
        pay, rec = -neg_pay, -neg_rec
        amount = min(pay, rec)
        moves.append(Move(payer, receiver, amount))
        if pay > amount:
            heapq.heappush(payers, (-(pay - amount), payer))
        if rec > amount:
            heapq.heappush(receivers, (-(rec - amount), receiver))
    if payers or receivers:
        raise AssertionError("positions do not sum to zero")
    return moves


class _Budget:
    def __init__(self, ops: int) -> None:
        self.left = ops
        self.used = 0

    def spend(self, n: int = 1) -> bool:
        self.left -= n
        self.used += n
        return self.left >= 0


def _zero_sum_groups(
    positions: dict[PartyKey, int], budget: _Budget
) -> tuple[list[list[PartyKey]], set[PartyKey]]:
    """Disjoint zero-sum groups of size 2, then 3, then 4, chosen deterministically."""
    live = {k: v for k, v in positions.items() if v != 0}
    groups: list[list[PartyKey]] = []

    def take(group: Iterable[PartyKey]) -> None:
        g = sorted(group)
        groups.append(g)
        for k in g:
            del live[k]

    # Exact pairs: a payer owing exactly what a receiver is owed.
    by_amount: dict[int, list[PartyKey]] = {}
    for k in sorted(live, key=lambda k: (-abs(live[k]), k)):
        if live[k] > 0:
            by_amount.setdefault(live[k], []).append(k)
    for k in sorted(live, key=lambda k: (-abs(live[k]), k)):
        if k not in live or live[k] >= 0:
            continue
        if not budget.spend():
            return groups, set(live)
        match = by_amount.get(-live[k])
        while match and match[0] not in live:
            match.pop(0)
        if match:
            take([k, match.pop(0)])

    # Subsets of 3 and 4: one side's party balanced by 2 or 3 parties on the other side.
    for size in (3, 4):
        progress = True
        while progress:
            progress = False
            keys = sorted(live, key=lambda k: (-abs(live[k]), k))
            for anchor in keys:
                anchor_amount = live[anchor]
                others = [k for k in keys if k != anchor and (live[k] > 0) != (anchor_amount > 0)]
                found = _subset_summing_to(-anchor_amount, others, live, size - 1, budget)
                if found is None and budget.left < 0:
                    return groups, set(live)
                if found:
                    take([anchor, *found])
                    progress = True
                    break
            # 2+2 groups (a pair of payers balancing a pair of receivers) for size 4.
            if not progress and size == 4:
                found2 = _pair_pair(live, budget)
                if found2:
                    take(found2)
                    progress = True
            if budget.left < 0:
                return groups, set(live)
    return groups, set(live)


def _subset_summing_to(
    target: int,
    candidates: list[PartyKey],
    live: dict[PartyKey, int],
    n: int,
    budget: _Budget,
) -> list[PartyKey] | None:
    if n == 2:
        seen: dict[int, PartyKey] = {}
        for k in candidates:
            if not budget.spend():
                return None
            want = target - live[k]
            if want in seen:
                return [seen[want], k]
            seen.setdefault(live[k], k)
        return None
    # n == 3: fix one candidate and solve a two-sum for the rest.
    for i, first in enumerate(candidates):
        rest = candidates[i + 1 :]
        found = _subset_summing_to(target - live[first], rest, live, 2, budget)
        if found:
            return [first, *found]
        if budget.left < 0:
            return None
    return None


def _pair_pair(live: dict[PartyKey, int], budget: _Budget) -> list[PartyKey] | None:
    payers = sorted((k for k in live if live[k] < 0), key=lambda k: (live[k], k))
    receivers = sorted((k for k in live if live[k] > 0), key=lambda k: (-live[k], k))
    receiver_pairs: dict[int, tuple[PartyKey, PartyKey]] = {}
    for a, b in combinations(receivers, 2):
        if not budget.spend():
            return None
        receiver_pairs.setdefault(live[a] + live[b], (a, b))
    for a, b in combinations(payers, 2):
        if not budget.spend():
            return None
        match = receiver_pairs.get(-(live[a] + live[b]))
        if match:
            return [a, b, *match]
    return None


def improved(positions: dict[PartyKey, int], time_budget_ms: int) -> tuple[list[Move], int]:
    """Zero-sum groups settled on their own, then greedy for what's left. Returns ops used."""
    budget = _Budget(max(time_budget_ms, 0) * OPS_PER_MS)
    groups, rest = _zero_sum_groups(positions, budget)
    moves: list[Move] = []
    for group in groups:
        moves.extend(greedy({k: positions[k] for k in group}))
    moves.extend(greedy({k: positions[k] for k in sorted(rest)}))
    return moves, budget.used
