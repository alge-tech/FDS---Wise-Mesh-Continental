"""Readers for a statement's stored content (PRD "Statement payload").

The stored content is the hashed, economic part of the payload. Code outside the builder
reads it through these helpers, so the shape is defined in one place.
"""

from collections.abc import Iterator, Mapping
from typing import Any
from uuid import UUID

HASH_PREFIX = "sha256:"


def invoices(content: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    for group in content["counterparties"]:
        yield from group["invoices"]


def invoice_ids(content: Mapping[str, Any]) -> set[UUID]:
    return {UUID(str(i["invoice_id"])) for i in invoices(content)}


def debit_credit(content: Mapping[str, Any]) -> tuple[int, int]:
    """What the member pays to, or receives from, Mesh settlement (fee included)."""
    instruction = content["instruction"]
    amount = int(instruction["amount"]["amount_minor"])
    if instruction["type"] == "DEBIT":
        return amount, 0
    if instruction["type"] == "CREDIT":
        return 0, amount
    return 0, 0


def settlement_currency(content: Mapping[str, Any]) -> str:
    return str(content["net"]["currency"])


def reference(run_id: UUID, member_id: UUID) -> str:
    """Payment reference for the statement's instruction. Stable across recomputes."""
    return f"MESH-{run_id.hex[:8].upper()}-{member_id.hex[:6].upper()}"
