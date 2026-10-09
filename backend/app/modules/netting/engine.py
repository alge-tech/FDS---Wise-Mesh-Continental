"""The netting engine: a pure function from a frozen input to a frozen, hashed result.

Pipeline (the PRD's order, corrected so FX runs before limits and transfers):
  1. canonicalise    drop excluded members and edges without a rate, sort, hash
  2. positions       receivables minus payables per member and currency (plus carry-in)
  3. FX pass         off-currency positions converted into each settlement currency
  4. limits          the largest over-limit payer is excluded and the engine restarts
  5. cycles          cancel directed cycles for the per-invoice trace
  6. dust            residuals below the threshold move to the CARRY pseudo-party
  7. transfers       greedy, kept only if the improvement pass doesn't beat it
  8. outcomes        cancelled + residual = outstanding for every included invoice
  9. validate, hash

Steps 2-6 and 8 run per connected component of the member graph (MC-NET-01), so a
component whose checks fail is dropped without blocking the others. Step 7 runs per
currency over every component, because the FX and CARRY pseudo-parties are shared.
"""

from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.enums import InvoiceOutcomeKind, PartyType, TransferKind
from app.core.hashing import hash_canonical
from app.core.money import convert_minor
from app.modules.netting import matching, validate
from app.modules.netting.cycles import cancel_cycles
from app.modules.netting.fx_pass import convert_positions, has_rate, lookup_rate
from app.modules.netting.types import (
    CARRY_PARTY,
    FX_PARTY,
    Cancellation,
    Carry,
    DroppedInvoice,
    Edge,
    EngineInput,
    EngineInvariantError,
    EngineResult,
    FxLeg,
    InvoiceOutcome,
    Metrics,
    NetPosition,
    PartyKey,
    PlannedTransfer,
)


def run_netting(inp: EngineInput) -> EngineResult:
    input_hash = hash_canonical(_canonical_input(inp))
    seed = int(input_hash[:16], 16)

    eligible, dropped = _eligible_edges(inp, set(inp.excluded_members))
    parts: list[_Component] = []
    errors: list[str] = []
    for component_edges in _components(eligible):
        try:
            parts.append(_compute_component(component_edges, inp))
        except EngineInvariantError as exc:
            # MC-NET-01: a failing component is left out; the others still net.
            errors.append(str(exc))
            dropped.extend(
                DroppedInvoice(e.invoice_id, "COMPONENT_FAILED") for e in component_edges
            )

    positions: dict[str, dict[PartyKey, int]] = defaultdict(lambda: defaultdict(int))
    edges: list[Edge] = []
    members: list[UUID] = []
    gross: dict[tuple[UUID, str], tuple[int, int]] = {}
    cancellations: list[Cancellation] = []
    outcomes: list[InvoiceOutcome] = []
    fx_legs: list[FxLeg] = []
    carries: list[Carry] = []
    carry_in_used: list[Carry] = []
    limit_excluded: list[UUID] = []
    cycles_cancelled = 0
    for part in parts:
        for currency, parties in part.positions.items():
            for key, amount in parties.items():
                positions[currency][key] += amount
        edges.extend(part.edges)
        members.extend(part.members)
        gross.update(part.gross)
        # Cycle numbers stay unique across components.
        cancellations.extend(
            replace(c, cycle_no=c.cycle_no + cycles_cancelled) for c in part.cancellations
        )
        cycles_cancelled += part.cycles
        outcomes.extend(part.outcomes)
        fx_legs.extend(part.fx_legs)
        carries.extend(part.carries)
        carry_in_used.extend(part.carry_in_used)
        limit_excluded.extend(part.limit_excluded)
        dropped.extend(part.dropped)
    merged = {c: dict(p) for c, p in sorted(positions.items())}
    members.sort(key=str)
    outcomes.sort(key=lambda o: str(o.invoice_id))
    validate.check_zero_sum(merged)

    # FX and CARRY pseudo-parties are shared by every component, so transfers are planned
    # per currency over all of them; planning per component would double those legs.
    transfers, greedy_count, improved_used, fallback, ops = _plan_transfers(merged, inp)

    net_positions = _net_positions(merged, members, carries, gross, inp)
    metrics = Metrics(
        invoice_count=len(edges),
        member_count=len(members),
        gross_minor=_sum_by_currency((e.currency, e.amount_minor) for e in edges),
        cancelled_minor=_cancelled_by_currency(tuple(edges), cancellations),
        net_minor=_sum_by_currency(
            (p.currency, p.amount_minor)
            for p in net_positions
            if p.party_type == PartyType.MEMBER and p.amount_minor > 0
        ),
        transfer_count=len(transfers),
        greedy_transfer_count=greedy_count,
        cycles_cancelled=cycles_cancelled,
        improved=improved_used,
        fallback_to_greedy=fallback,
        limit_restarts=len(limit_excluded),
        dust_carried=len(carries),
        improvement_ops=ops,
        component_count=len(parts) + len(errors),
        failed_components=len(errors),
    )
    result = EngineResult(
        positions=tuple(net_positions),
        transfers=tuple(transfers),
        cancellations=tuple(cancellations),
        outcomes=tuple(outcomes),
        fx_legs=tuple(sorted(fx_legs, key=lambda f: (str(f.member_id), f.from_currency))),
        carries=tuple(carries),
        carry_in_used=tuple(carry_in_used),
        dropped=tuple(sorted(dropped, key=lambda d: str(d.invoice_id))),
        limit_excluded=tuple(limit_excluded),
        metrics=metrics,
        input_hash=input_hash,
        result_hash="",
        seed=seed,
        component_errors=tuple(errors),
    )
    return replace(result, result_hash=hash_canonical(_canonical_result(result, inp)))


@dataclass(frozen=True)
class _Component:
    edges: tuple[Edge, ...]
    positions: dict[str, dict[PartyKey, int]]
    members: list[UUID]
    gross: dict[tuple[UUID, str], tuple[int, int]]
    cancellations: list[Cancellation]
    cycles: int
    outcomes: list[InvoiceOutcome]
    fx_legs: list[FxLeg]
    carries: list[Carry]
    carry_in_used: list[Carry]
    limit_excluded: list[UUID]
    dropped: list[DroppedInvoice]


def _components(edges: tuple[Edge, ...]) -> list[tuple[Edge, ...]]:
    """MC-NET-01: split the invoices into connected components of the member graph.

    A member's position depends only on its own component, so each one nets on its own.
    Components come out ordered by their smallest member ID, edges in canonical order.
    """
    parent: dict[UUID, UUID] = {}

    def root(m: UUID) -> UUID:
        parent.setdefault(m, m)
        while parent[m] != m:
            parent[m] = parent[parent[m]]
            m = parent[m]
        return m

    for e in edges:
        a, b = root(e.payer), root(e.receiver)
        if a != b:
            parent[max(a, b, key=str)] = min(a, b, key=str)
    groups: dict[UUID, list[Edge]] = defaultdict(list)
    for e in edges:
        groups[root(e.payer)].append(e)
    # Union by smallest ID makes each root its component's smallest member.
    return [tuple(groups[r]) for r in sorted(groups, key=str)]


def _compute_component(component_edges: tuple[Edge, ...], inp: EngineInput) -> _Component:
    """Steps 2-6 and 8 for one component. Raises EngineInvariantError if a check fails."""
    excluded: set[UUID] = set()
    limit_excluded: list[UUID] = []
    while True:
        edges = tuple(
            e for e in component_edges if e.payer not in excluded and e.receiver not in excluded
        )
        positions, members, gross, carry_in_used = _positions(edges, inp)
        fx_legs = convert_positions(
            positions,
            {str(m): m for m in members},
            {str(m): inp.settlement_currency[m] for m in members},
            inp.rates,
            inp.currency_exponents,
        )
        over = _largest_over_limit(positions, members, inp)
        if over is None:
            break
        excluded.add(over)
        limit_excluded.append(over)

    cancellations, cycles = cancel_cycles(edges)
    carries = _apply_dust(positions, members, inp)
    validate.check_zero_sum(positions)
    outcomes = _outcomes(edges, cancellations)
    validate.check_outcomes(edges, cancellations, outcomes)
    return _Component(
        edges=edges,
        positions=positions,
        members=members,
        gross=gross,
        cancellations=cancellations,
        cycles=cycles,
        outcomes=outcomes,
        fx_legs=fx_legs,
        carries=carries,
        carry_in_used=carry_in_used,
        limit_excluded=limit_excluded,
        dropped=[
            DroppedInvoice(e.invoice_id, "LIMIT_EXCEEDED")
            for e in component_edges
            if e.payer in excluded or e.receiver in excluded
        ],
    )


# --- 1. canonicalise ------------------------------------------------------------------


def _edge_key(e: Edge) -> tuple[str, str, str, str]:
    return (e.currency, str(e.payer), str(e.receiver), str(e.invoice_id))


def _canonical_input(inp: EngineInput) -> dict[str, Any]:
    edges = sorted(
        (
            e
            for e in inp.edges
            if e.payer not in inp.excluded_members and e.receiver not in inp.excluded_members
        ),
        key=_edge_key,
    )
    return {
        "algo_version": inp.algo_version,
        "edges": [
            [str(e.invoice_id), str(e.payer), str(e.receiver), e.amount_minor, e.currency]
            for e in edges
        ],
        "rates": sorted([b, q, str(r)] for (b, q), r in inp.rates.items()),
        "settlement_currency": sorted([str(m), c] for m, c in inp.settlement_currency.items()),
        "payable_limit_minor": sorted([str(m), v] for m, v in inp.payable_limit_minor.items()),
        "excluded_members": sorted(str(m) for m in inp.excluded_members),
        "exponents": sorted([c, x] for c, x in inp.currency_exponents.items()),
        "dust_threshold_minor": inp.dust_threshold_minor,
        "carry_in": sorted([str(c.member), c.currency, c.amount_minor] for c in inp.carry_in),
        "time_budget_ms": inp.time_budget_ms,
    }


def _eligible_edges(
    inp: EngineInput, excluded: set[UUID]
) -> tuple[tuple[Edge, ...], list[DroppedInvoice]]:
    kept: list[Edge] = []
    dropped: list[DroppedInvoice] = []
    for e in sorted(inp.edges, key=_edge_key):
        if e.amount_minor <= 0:
            raise EngineInvariantError("edge amounts must be positive")
        if e.payer == e.receiver:
            raise EngineInvariantError("an invoice cannot have the same payer and receiver")
        if e.payer in excluded or e.receiver in excluded:
            if e.payer in inp.excluded_members or e.receiver in inp.excluded_members:
                dropped.append(DroppedInvoice(e.invoice_id, "MEMBER_EXCLUDED"))
            continue
        needs = {inp.settlement_currency[e.payer], inp.settlement_currency[e.receiver]}
        if not all(has_rate(inp.rates, e.currency, target) for target in needs):
            dropped.append(DroppedInvoice(e.invoice_id, "NO_RATE"))
            continue
        kept.append(e)
    return tuple(kept), dropped


# --- 2. positions ---------------------------------------------------------------------


def _positions(
    edges: tuple[Edge, ...], inp: EngineInput
) -> tuple[
    dict[str, dict[PartyKey, int]],
    list[UUID],
    dict[tuple[UUID, str], tuple[int, int]],
    list[Carry],
]:
    positions: dict[str, dict[PartyKey, int]] = defaultdict(lambda: defaultdict(int))
    gross_in: dict[tuple[UUID, str], int] = defaultdict(int)
    gross_out: dict[tuple[UUID, str], int] = defaultdict(int)
    members: set[UUID] = set()
    for e in edges:
        positions[e.currency][str(e.receiver)] += e.amount_minor
        positions[e.currency][str(e.payer)] -= e.amount_minor
        gross_in[(e.receiver, e.currency)] += e.amount_minor
        gross_out[(e.payer, e.currency)] += e.amount_minor
        members.update((e.payer, e.receiver))
    carry_in_used: list[Carry] = []
    for c in sorted(inp.carry_in, key=lambda c: (str(c.member), c.currency)):
        if c.member in members and c.amount_minor:
            positions[c.currency][str(c.member)] += c.amount_minor
            positions[c.currency][CARRY_PARTY] -= c.amount_minor
            carry_in_used.append(Carry(c.member, c.currency, c.amount_minor))
    totals: dict[UUID, list[int]] = {m: [0, 0] for m in members}
    for side, source in ((0, gross_in), (1, gross_out)):
        for (member, currency), amount in source.items():
            target = inp.settlement_currency[member]
            totals[member][side] += _to(amount, currency, target, inp)
    gross = {(m, inp.settlement_currency[m]): (t[0], t[1]) for m, t in totals.items()}
    plain = {c: dict(parties) for c, parties in positions.items()}
    return plain, sorted(members, key=str), gross, carry_in_used


def _to(amount: int, currency: str, target: str, inp: EngineInput) -> int:
    if currency == target:
        return amount
    rate = lookup_rate(inp.rates, currency, target)
    return convert_minor(
        amount, rate, inp.currency_exponents.get(currency, 2), inp.currency_exponents.get(target, 2)
    )


# --- 4. limits ------------------------------------------------------------------------


def _largest_over_limit(
    positions: dict[str, dict[PartyKey, int]], members: list[UUID], inp: EngineInput
) -> UUID | None:
    worst: tuple[int, str, UUID] | None = None
    for m in members:
        limit = inp.payable_limit_minor.get(m)
        if limit is None:
            continue
        payable = -positions.get(inp.settlement_currency[m], {}).get(str(m), 0)
        overage = payable - limit
        if overage > 0:
            candidate = (-overage, str(m), m)
            if worst is None or candidate < worst:
                worst = candidate
    return worst[2] if worst else None


# --- 6. dust --------------------------------------------------------------------------


def _apply_dust(
    positions: dict[str, dict[PartyKey, int]], members: list[UUID], inp: EngineInput
) -> list[Carry]:
    carries: list[Carry] = []
    if inp.dust_threshold_minor <= 0:
        return carries
    for m in members:
        currency = inp.settlement_currency[m]
        amount = positions.get(currency, {}).get(str(m), 0)
        if amount != 0 and abs(amount) < inp.dust_threshold_minor:
            positions[currency][str(m)] = 0
            positions[currency][CARRY_PARTY] = positions[currency].get(CARRY_PARTY, 0) + amount
            carries.append(Carry(m, currency, amount))
    return carries


# --- 7. transfers ---------------------------------------------------------------------


def _plan_transfers(
    positions: dict[str, dict[PartyKey, int]], inp: EngineInput
) -> tuple[list[PlannedTransfer], int, bool, bool, int]:
    transfers: list[PlannedTransfer] = []
    greedy_total = 0
    any_improved = False
    fallback = False
    ops_total = 0
    for currency in sorted(positions):
        live = {k: v for k, v in sorted(positions[currency].items()) if v != 0}
        base = matching.greedy(live)
        validate.check_plan_clears(currency, live, base)
        greedy_total += len(base)
        chosen = base
        if inp.time_budget_ms > 0 and len(live) > 2:
            better, ops = matching.improved(live, inp.time_budget_ms)
            ops_total += ops
            if len(better) < len(base):
                try:
                    validate.check_plan_clears(currency, live, better)
                    chosen = better
                    any_improved = True
                except EngineInvariantError:
                    fallback = True
        transfers.extend(_to_transfer(currency, m) for m in chosen)
    transfers.sort(
        key=lambda t: (
            t.currency,
            t.kind,
            str(t.payer_member_id),
            str(t.receiver_member_id),
            t.payer_type,
            t.receiver_type,
            t.amount_minor,
        )
    )
    return transfers, greedy_total, any_improved, fallback, ops_total


def _party(key: PartyKey) -> tuple[PartyType, UUID | None]:
    if key == FX_PARTY:
        return PartyType.FX, None
    if key == CARRY_PARTY:
        return PartyType.CARRY, None
    return PartyType.MEMBER, UUID(key)


def _to_transfer(currency: str, move: matching.Move) -> PlannedTransfer:
    payer_type, payer = _party(move.payer)
    receiver_type, receiver = _party(move.receiver)
    kind = (
        TransferKind.FX_LEG
        if PartyType.FX in (payer_type, receiver_type)
        else TransferKind.SETTLEMENT
    )
    return PlannedTransfer(
        payer_type, payer, receiver_type, receiver, currency, move.amount_minor, kind
    )


# --- 8. outcomes ----------------------------------------------------------------------


def _outcomes(edges: tuple[Edge, ...], cancellations: list[Cancellation]) -> list[InvoiceOutcome]:
    cancelled: dict[UUID, int] = defaultdict(int)
    for c in cancellations:
        cancelled[c.invoice_id] += c.amount_minor
    out = []
    for e in sorted(edges, key=lambda e: str(e.invoice_id)):
        done = cancelled.get(e.invoice_id, 0)
        residual = e.amount_minor - done
        out.append(
            InvoiceOutcome(
                e.invoice_id,
                e.amount_minor,
                done,
                residual,
                InvoiceOutcomeKind.SETTLED_BY_NETTING
                if residual == 0
                else InvoiceOutcomeKind.SETTLED_BY_TRANSFER,
            )
        )
    return out


# --- result assembly ------------------------------------------------------------------


def _net_positions(
    positions: dict[str, dict[PartyKey, int]],
    members: list[UUID],
    carries: list[Carry],
    gross: dict[tuple[UUID, str], tuple[int, int]],
    inp: EngineInput,
) -> list[NetPosition]:
    carried = {(c.member_id, c.currency): c.amount_minor for c in carries}
    out: list[NetPosition] = []
    for m in members:
        currency = inp.settlement_currency[m]
        g_in, g_out = gross.get((m, currency), (0, 0))
        out.append(
            NetPosition(
                PartyType.MEMBER,
                m,
                currency,
                positions.get(currency, {}).get(str(m), 0),
                carried.get((m, currency), 0),
                g_in,
                g_out,
            )
        )
    for currency in sorted(positions):
        for key, party_type in ((FX_PARTY, PartyType.FX), (CARRY_PARTY, PartyType.CARRY)):
            amount = positions[currency].get(key, 0)
            if amount:
                out.append(NetPosition(party_type, None, currency, amount))
    out.sort(key=lambda p: (p.currency, p.party_type, str(p.member_id)))
    return out


def _sum_by_currency(items: Any) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for currency, amount in items:
        totals[currency] += amount
    return dict(sorted(totals.items()))


def _cancelled_by_currency(
    edges: tuple[Edge, ...], cancellations: list[Cancellation]
) -> dict[str, int]:
    currency_of = {e.invoice_id: e.currency for e in edges}
    return _sum_by_currency((currency_of[c.invoice_id], c.amount_minor) for c in cancellations)


def _canonical_result(result: EngineResult, inp: EngineInput) -> dict[str, Any]:
    def fx(leg: FxLeg) -> list[Any]:
        return [
            str(leg.member_id),
            leg.from_currency,
            leg.from_amount_minor,
            leg.to_currency,
            leg.to_amount_minor,
            str(Decimal(leg.rate)),
        ]

    return {
        "algo_version": inp.algo_version,
        "input_hash": result.input_hash,
        "positions": [
            [p.party_type, str(p.member_id), p.currency, p.amount_minor, p.carried_minor]
            for p in result.positions
        ],
        "transfers": [
            [
                t.payer_type,
                str(t.payer_member_id),
                t.receiver_type,
                str(t.receiver_member_id),
                t.currency,
                t.amount_minor,
                t.kind,
            ]
            for t in result.transfers
        ],
        "cancellations": [
            [str(c.invoice_id), c.cycle_no, c.amount_minor] for c in result.cancellations
        ],
        "outcomes": [
            [str(o.invoice_id), o.cancelled_minor, o.residual_minor, o.outcome]
            for o in result.outcomes
        ],
        "fx_legs": [fx(leg) for leg in result.fx_legs],
        "carries": [[str(c.member_id), c.currency, c.amount_minor] for c in result.carries],
        "carry_in_used": [
            [str(c.member_id), c.currency, c.amount_minor] for c in result.carry_in_used
        ],
        "dropped": [[str(d.invoice_id), d.reason] for d in result.dropped],
        "limit_excluded": [str(m) for m in result.limit_excluded],
    }
