"""Network graphs: the whole mesh for Wise staff, the member's own edges for members."""

from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import InvoiceStatus, PartyType
from app.core.errors import NotFound
from app.modules.invoices.models import Invoice
from app.modules.invoices.repository import involves
from app.modules.members.models import LegalEntity, Member
from app.modules.network.schemas import GraphEdge, GraphNode, NetworkView, RunChoice
from app.modules.runs import repository
from app.modules.runs.models import NettingRun, PlannedTransfer
from app.modules.settlement.schemas import MESH_COUNTERPARTY
from app.modules.statements import content as statement_content
from app.modules.statements.models import Statement
from app.modules.windows.eligibility import eligible
from app.modules.windows.models import RunInvoice, Window

FX_NODE, CARRY_NODE, MESH_NODE, SELF_NODE = "fx", "carry", "mesh", "self"


def _aggregate(rows: Iterable[tuple[str, str, str, int]]) -> list[GraphEdge]:
    """(payer, receiver, currency, amount) -> one edge per pair and currency."""
    sums: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0])
    for payer, receiver, currency, amount in rows:
        slot = sums[(payer, receiver, currency)]
        slot[0] += amount
        slot[1] += 1
    return [
        GraphEdge(
            id=f"inv:{p}:{r}:{c}",
            source=p,
            target=r,
            currency=c,
            amount_minor=amount,
            invoice_count=count,
            kind="INVOICE",
        )
        for (p, r, c), (amount, count) in sorted(sums.items())
    ]


def _totals(edges: list[GraphEdge]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for e in edges:
        out[e.currency] += e.amount_minor
    return dict(sorted(out.items()))


def _runs(session: Session) -> list[NettingRun]:
    return list(session.scalars(select(NettingRun).order_by(NettingRun.started_at.desc())))


def admin_network(session: Session, run_id: UUID | None) -> NetworkView:
    names = dict(session.execute(select(Member.id, Member.display_name)).tuples().all())
    all_runs = _runs(session)
    run = next((r for r in all_runs if r.id == run_id), None) if run_id else None
    if run_id and run is None:
        raise NotFound()
    run = run or (all_runs[0] if all_runs else None)
    transfers: list[GraphEdge] = []
    if run is not None:
        computation = repository.latest(session, run)
        statements = (
            list(
                session.scalars(select(Statement).where(Statement.computation_id == computation.id))
            )
            if computation
            else []
        )
        included = {str(i) for s in statements for i in statement_content.invoice_ids(s.content)}
        frozen = list(
            session.scalars(
                select(RunInvoice)
                .where(RunInvoice.run_id == run.id)
                .order_by(RunInvoice.invoice_id)
            )
        )
        # Before netting: the invoices the current computation nets (all frozen ones if none).
        invoice_edges = _aggregate(
            (str(r.payer_member_id), str(r.receiver_member_id), r.currency, r.outstanding_minor)
            for r in frozen
            if not included or str(r.invoice_id) in included
        )
        if computation:
            for n, t in enumerate(
                session.scalars(
                    select(PlannedTransfer)
                    .where(PlannedTransfer.computation_id == computation.id)
                    .order_by(PlannedTransfer.currency, PlannedTransfer.amount_minor.desc())
                )
            ):
                transfers.append(
                    GraphEdge(
                        id=f"tr:{n}",
                        source=_node_id(t.payer_party, t.payer_member_id),
                        target=_node_id(t.receiver_party, t.receiver_member_id),
                        currency=t.currency,
                        amount_minor=t.amount_minor,
                        kind="FX_LEG" if t.kind == "FX_LEG" else "SETTLEMENT",
                    )
                )
        source = "RUN"
    else:
        window = session.scalar(select(Window).where(Window.status == "OPEN"))
        candidates = eligible(session, window)[0] if window else []
        invoice_edges = _aggregate(
            (str(i.payer_member_id), str(i.issuer_member_id), i.currency, i.outstanding_minor)
            for i in candidates
        )
        source = "WINDOW"
    ids = sorted(
        {e.source for e in invoice_edges + transfers}
        | {e.target for e in invoice_edges + transfers}
    )
    nodes = [_node(i, names) for i in ids]
    nodes.sort(key=lambda n: (n.kind != "MEMBER", n.label))
    return NetworkView(
        source=source,
        run_id=run.id if run else None,
        run_status=run.status if run else None,
        attempt=run.current_attempt if run else None,
        nodes=nodes,
        invoice_edges=invoice_edges,
        transfer_edges=transfers,
        gross_minor=_totals(invoice_edges),
        net_minor=_totals([t for t in transfers if t.kind == "SETTLEMENT"]),
        runs=[RunChoice(id=r.id, status=r.status, started_at=r.started_at) for r in all_runs],
    )


def _node_id(party: str, member_id: UUID | None) -> str:
    if party == PartyType.FX:
        return FX_NODE
    if party == PartyType.CARRY:
        return CARRY_NODE
    return str(member_id)


def _node(node_id: str, names: dict[UUID, str]) -> GraphNode:
    if node_id == FX_NODE:
        return GraphNode(id=node_id, label="Mesh FX", kind="FX")
    if node_id == CARRY_NODE:
        return GraphNode(id=node_id, label="Carry forward", kind="CARRY")
    return GraphNode(id=node_id, label=names.get(UUID(node_id), "Member"), kind="MEMBER")


def member_network(session: Session, member_id: UUID) -> NetworkView:
    """Own counterparties and own flows only (G7, MC-PRV-02).

    Invoice edges come from the member's own invoices. The only transfer is the member's own
    settlement with Mesh settlement in its latest run; who else paid or received is never shown.
    """
    member = session.get(Member, member_id)
    assert member is not None
    nodes = {SELF_NODE: GraphNode(id=SELF_NODE, label=member.display_name, kind="SELF")}
    rows = []
    for i in session.scalars(
        select(Invoice)
        .where(
            involves(member_id),
            Invoice.status.not_in([InvoiceStatus.REJECTED_DATA, InvoiceStatus.CANCELLED]),
        )
        .order_by(Invoice.id)
    ):
        receivable = i.issuer_member_id == member_id
        entity_id = i.payer_entity_id if receivable else i.issuer_entity_id
        other_member = i.payer_member_id if receivable else i.issuer_member_id
        entity = session.get(LegalEntity, entity_id) if entity_id else None
        raw = i.counterparty_raw["payer_tax_id" if receivable else "issuer_tax_id"]
        other = f"cp:{other_member}" if other_member else f"ext:{raw}"
        nodes.setdefault(
            other,
            GraphNode(
                id=other, label=entity.legal_name if entity else str(raw), kind="COUNTERPARTY"
            ),
        )
        rows.append(
            (other, SELF_NODE, i.currency, i.outstanding_minor)
            if receivable
            else (SELF_NODE, other, i.currency, i.outstanding_minor)
        )
    invoice_edges = _aggregate(rows)
    transfers: list[GraphEdge] = []
    latest = None
    for run in repository.list_for_member(session, member_id):
        computation = repository.latest(session, run)
        statement = (
            session.scalar(
                select(Statement).where(
                    Statement.computation_id == computation.id, Statement.member_id == member_id
                )
            )
            if computation
            else None
        )
        if statement is None:
            continue
        latest = run
        c = statement.content
        debit, credit = statement_content.debit_credit(c)
        if debit or credit:
            nodes[MESH_NODE] = GraphNode(id=MESH_NODE, label=MESH_COUNTERPARTY, kind="MESH")
            transfers.append(
                GraphEdge(
                    id="tr:own",
                    source=SELF_NODE if debit else MESH_NODE,
                    target=MESH_NODE if debit else SELF_NODE,
                    currency=statement_content.settlement_currency(c),
                    amount_minor=debit or credit,
                    kind="SETTLEMENT",
                )
            )
        break
    return NetworkView(
        source="MEMBER",
        run_id=latest.id if latest else None,
        run_status=latest.status if latest else None,
        attempt=latest.current_attempt if latest else None,
        nodes=sorted(nodes.values(), key=lambda n: (n.kind != "SELF", n.kind, n.label)),
        invoice_edges=invoice_edges,
        transfer_edges=transfers,
        gross_minor=_totals(invoice_edges),
        net_minor=_totals(transfers),
        runs=[],
    )
