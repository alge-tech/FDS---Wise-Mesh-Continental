"""MC-RSK-02 ring rule. Pure: no database access.

A ring is a directed cycle of invoices whose members all joined recently and whose amounts
are round and equal: the shape of circular invoicing between new shell companies. Equal
amounts mean a ring lives inside one (currency, amount) group, so each group is searched on
its own, with the same deterministic cycle search the netting engine uses.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from uuid import UUID

import networkx as nx


@dataclass(frozen=True)
class RingInvoice:
    invoice_id: UUID
    payer: UUID
    receiver: UUID
    currency: str
    amount_minor: int


def find_rings(
    invoices: Iterable[RingInvoice],
    recent_members: set[UUID],
    round_unit_minor: Mapping[str, int],
) -> list[tuple[RingInvoice, ...]]:
    """Every ring, each invoice in at most one. Same input, same rings, same order."""
    groups: dict[tuple[str, int], dict[tuple[str, str], list[RingInvoice]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for i in sorted(invoices, key=lambda i: str(i.invoice_id)):
        unit = round_unit_minor.get(i.currency)
        if (
            unit
            and i.amount_minor % unit == 0
            and i.payer in recent_members
            and i.receiver in recent_members
        ):
            groups[(i.currency, i.amount_minor)][(str(i.payer), str(i.receiver))].append(i)

    rings: list[tuple[RingInvoice, ...]] = []
    for key in sorted(groups):
        pairs = groups[key]
        graph: nx.DiGraph = nx.DiGraph()
        graph.add_edges_from(sorted(pairs))
        while True:
            cyclic = sorted(
                (c for c in nx.strongly_connected_components(graph) if len(c) > 1), key=min
            )
            if not cyclic:
                break
            component = cyclic[0]
            cycle = nx.find_cycle(graph.subgraph(component), source=min(component))
            ring = []
            for u, v in cycle:
                ring.append(pairs[(u, v)].pop(0))
                if not pairs[(u, v)]:
                    graph.remove_edge(u, v)
            rings.append(tuple(ring))
    return rings
