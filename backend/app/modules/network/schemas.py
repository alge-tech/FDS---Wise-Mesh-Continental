from datetime import datetime
from typing import Literal
from uuid import UUID

from app.core.schemas import ApiModel

NodeKind = Literal["MEMBER", "SELF", "COUNTERPARTY", "MESH", "FX", "CARRY"]


class GraphNode(ApiModel):
    id: str
    label: str
    kind: NodeKind


class GraphEdge(ApiModel):
    """Invoice edges point from payer to receiver (issuer); so do transfer edges."""

    id: str
    source: str
    target: str
    currency: str
    amount_minor: int
    invoice_count: int = 0
    kind: Literal["INVOICE", "SETTLEMENT", "FX_LEG"]


class RunChoice(ApiModel):
    id: UUID
    status: str
    started_at: datetime


class NetworkView(ApiModel):
    source: Literal["RUN", "WINDOW", "MEMBER"]
    run_id: UUID | None
    run_status: str | None
    attempt: int | None
    nodes: list[GraphNode]
    invoice_edges: list[GraphEdge]  # before netting: gross invoices
    transfer_edges: list[GraphEdge]  # after netting: settlement transfers
    gross_minor: dict[str, int]
    net_minor: dict[str, int]
    runs: list[RunChoice]
