from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.core.schemas import ApiModel, StrictModel


class InvoiceCreate(StrictModel):
    invoice_number: str
    issuer_tax_id: str
    payer_tax_id: str
    currency: str
    amount: str
    outstanding: str = ""
    issue_date: str
    due_date: str


class Correction(StrictModel):
    amount: str | None = None
    outstanding: str | None = None
    due_date: str | None = None
    invoice_number: str | None = None


class ConfirmationRequest(StrictModel):
    decision: Literal["CONFIRM", "DISPUTE", "CORRECT"]
    version: int = Field(ge=1)
    reason_code: str | None = None
    corrected_fields: Correction | None = None


class InvoiceView(ApiModel):
    id: UUID
    invoice_number: str
    issue_date: date
    due_date: date
    currency: str
    amount_minor: int
    outstanding_minor: int
    status: str
    current_version: int
    direction: str
    counterparty: str
    counterparty_member_id: UUID | None
    issuer_tax_id: str
    payer_tax_id: str
    needs_confirmation: bool


class InvoiceDetail(InvoiceView):
    versions: list[dict[str, Any]]
    confirmations: list[dict[str, Any]]
    exclusions: list[dict[str, Any]]
    outcomes: list[dict[str, Any]]
    audit: list[dict[str, Any]]


class UploadError(ApiModel):
    row: int
    field: str
    reason: str


class UploadResult(ApiModel):
    items: list[InvoiceView]
    errors: list[UploadError]


class CounterpartyView(ApiModel):
    identity: str
    name: str
    member_id: UUID | None
    status: str
    invoice_count: int
