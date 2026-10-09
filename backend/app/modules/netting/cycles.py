"""Cycle cancellation (MC-NET-01, MC-NET-02).

Positions don't change when a cycle is cancelled, so this pass only produces the
per-invoice trace (which invoices were settled by netting, and by how much). It runs per
currency on a graph whose parallel invoices are merged per (payer, receiver). Cycles are
found with a depth-first search from the smallest node of each strongly connected
component, so the same input always cancels the same cycles in the same order.
"""

from collections import defaultdict
from dataclasses import dataclass, field

import networkx as nx

from app.modules.netting.types import Cancellation, Edge


@dataclass
class _Bundle:
    """The invoices between one ordered pair of members, consumed in invoice_id order."""

    invoices: list[tuple[str, Edge]]  # (sort key, edge)
    remaining: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.remaining = [e.amount_minor for _, e in self.invoices]

    def cancel(self, amount: int, cycle_no: int, out: list[Cancellation]) -> None:
        for idx, (_, edge) in enumerate(self.invoices):
            if amount == 0:
                return
            take = min(amount, self.remaining[idx])
            if take:
                self.remaining[idx] -= take
                amount -= take
                out.append(Cancellation(edge.invoice_id, cycle_no, take))
        if amount:
            raise AssertionError("cancelled more than the bundle holds")


def cancel_cycles(edges: tuple[Edge, ...]) -> tuple[list[Cancellation], int]:
    """Cancel directed cycles until every currency graph is acyclic.

    Returns the cancellations (one per invoice per cycle it took part in) and the number
    of cycles cancelled. `edges` must already be sorted canonically.
    """
    by_currency: dict[str, dict[tuple[str, str], list[tuple[str, Edge]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for e in edges:
        by_currency[e.currency][(str(e.payer), str(e.receiver))].append((str(e.invoice_id), e))

    cancellations: list[Cancellation] = []
    cycle_no = 0
    for currency in sorted(by_currency):
        pairs = by_currency[currency]
        bundles = {pair: _Bundle(sorted(invs, key=lambda t: t[0])) for pair, invs in pairs.items()}
        graph: nx.DiGraph = nx.DiGraph()
        graph.add_nodes_from(sorted({n for pair in pairs for n in pair}))
        for pair in sorted(pairs):
            graph.add_edge(*pair, weight=sum(bundles[pair].remaining))

        for component in _cyclic_components(graph):
            sub = graph.subgraph(component)
            start = sorted(component)
            while True:
                try:
                    cycle = nx.find_cycle(sub, source=start)
                except nx.NetworkXNoCycle:
                    break
                cycle_no += 1
                amount = min(graph.edges[u, v]["weight"] for u, v in cycle)
                for u, v in cycle:
                    bundles[(u, v)].cancel(amount, cycle_no, cancellations)
                    graph.edges[u, v]["weight"] -= amount
                    if graph.edges[u, v]["weight"] == 0:
                        graph.remove_edge(u, v)
    return cancellations, cycle_no


def _cyclic_components(graph: nx.DiGraph) -> list[frozenset[str]]:
    """Strongly connected components that can contain a cycle, smallest node first.

    Cancelling never adds edges, so no new cycle can appear across components and each
    component can be exhausted on its own.
    """
    comps = [frozenset(c) for c in nx.strongly_connected_components(graph) if len(c) > 1]
    return sorted(comps, key=min)
