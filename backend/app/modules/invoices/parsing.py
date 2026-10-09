"""CSV and manual-form validation (MC-ING-01, MC-ING-02). Pure: no database access.

Amounts go straight from the decimal string to integer minor units with the currency's
exponent; there is no float step and no rounding.
"""

import csv
import io
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date

from app.core.hashing import sha256_hex
from app.core.money import MoneyParseError, format_minor, parse_minor

TEMPLATE_COLUMNS = (
    "invoice_number",
    "issuer_tax_id",
    "payer_tax_id",
    "currency",
    "amount",
    "outstanding",
    "issue_date",
    "due_date",
)
MAX_INVOICE_NUMBER = 64


@dataclass(frozen=True)
class RowError:
    row: int
    field: str
    reason: str


@dataclass(frozen=True)
class ParsedInvoice:
    row: int
    invoice_number: str
    issuer_tax_id: str
    payer_tax_id: str
    currency: str
    amount_minor: int
    outstanding_minor: int
    issue_date: date
    due_date: date

    @property
    def fingerprint(self) -> str:
        return fingerprint(
            self.issuer_tax_id,
            self.payer_tax_id,
            self.invoice_number,
            self.issue_date,
            self.currency,
            self.amount_minor,
        )


def normalise_tax_id(value: str) -> str:
    return re.sub(r"[\s\-.]", "", value).upper()


def normalise_invoice_number(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().upper()


def fingerprint(
    issuer_tax_id: str,
    payer_tax_id: str,
    invoice_number: str,
    issue_date: date,
    currency: str,
    amount_minor: int,
) -> str:
    """MC-ING-04: SHA-256 over the normalised identity of an invoice."""
    parts = [
        normalise_tax_id(issuer_tax_id),
        normalise_tax_id(payer_tax_id),
        normalise_invoice_number(invoice_number),
        issue_date.isoformat(),
        currency.upper(),
        str(amount_minor),
    ]
    return sha256_hex("|".join(parts))


def _date(value: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        raise ValueError("must be a date in YYYY-MM-DD format")
    return date.fromisoformat(value.strip())


def invoice_minor(value: str, exponent: int) -> int:
    if len(value) > 24:
        raise MoneyParseError("amount is too large")
    result = parse_minor(value, exponent)
    if result > 2**63 - 1:
        raise MoneyParseError("amount is too large")
    return result


def validate_row(
    raw: Mapping[str, str | None], row: int, exponents: Mapping[str, int]
) -> ParsedInvoice | list[RowError]:
    """Validate one row. Returns every field error found, not just the first."""
    errors: list[RowError] = []

    def get(name: str) -> str:
        return (raw.get(name) or "").strip()

    number = get("invoice_number")
    if not number:
        errors.append(RowError(row, "invoice_number", "is required"))
    elif len(number) > MAX_INVOICE_NUMBER:
        errors.append(RowError(row, "invoice_number", f"is longer than {MAX_INVOICE_NUMBER}"))

    issuer = normalise_tax_id(get("issuer_tax_id"))
    payer = normalise_tax_id(get("payer_tax_id"))
    if not issuer:
        errors.append(RowError(row, "issuer_tax_id", "is required"))
    if not payer:
        errors.append(RowError(row, "payer_tax_id", "is required"))
    if issuer and payer and issuer == payer:
        errors.append(RowError(row, "payer_tax_id", "must differ from the issuer"))

    currency = get("currency").upper()
    exponent = exponents.get(currency)
    if exponent is None:
        errors.append(RowError(row, "currency", f"must be one of {', '.join(sorted(exponents))}"))

    amount_minor = outstanding_minor = 0
    if exponent is not None:
        try:
            amount_minor = invoice_minor(get("amount"), exponent)
            if amount_minor <= 0:
                errors.append(RowError(row, "amount", "must be greater than zero"))
        except MoneyParseError as exc:
            errors.append(RowError(row, "amount", str(exc)))
        outstanding_raw = get("outstanding")
        if not outstanding_raw:
            outstanding_minor = amount_minor
        else:
            try:
                outstanding_minor = invoice_minor(outstanding_raw, exponent)
                if outstanding_minor <= 0:
                    errors.append(RowError(row, "outstanding", "must be greater than zero"))
                elif amount_minor and outstanding_minor > amount_minor:
                    errors.append(RowError(row, "outstanding", "must not exceed the amount"))
            except MoneyParseError as exc:
                errors.append(RowError(row, "outstanding", str(exc)))

    issue_date = due_date = None
    for field_name in ("issue_date", "due_date"):
        try:
            parsed = _date(get(field_name))
        except ValueError as exc:
            reason = str(exc) if "format" in str(exc) else "is not a valid date"
            errors.append(RowError(row, field_name, reason))
            continue
        if field_name == "issue_date":
            issue_date = parsed
        else:
            due_date = parsed
    if issue_date and due_date and due_date < issue_date:
        errors.append(RowError(row, "due_date", "must not be before the issue date"))

    if errors:
        return errors
    assert issue_date is not None and due_date is not None
    return ParsedInvoice(
        row=row,
        invoice_number=number,
        issuer_tax_id=issuer,
        payer_tax_id=payer,
        currency=currency,
        amount_minor=amount_minor,
        outstanding_minor=outstanding_minor,
        issue_date=issue_date,
        due_date=due_date,
    )


class CsvShapeError(ValueError):
    pass


def read_csv(content: bytes, max_rows: int) -> Iterator[tuple[int, dict[str, str | None]]]:
    """Yield (row number, raw row). Row 1 is the header, so data starts at row 2."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvShapeError("The file must be UTF-8 encoded CSV.") from exc
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in TEMPLATE_COLUMNS if c not in header]
    if missing:
        raise CsvShapeError(f"Missing columns: {', '.join(missing)}. Use the template.")
    if len(header) != len(set(header)):
        raise CsvShapeError("Column names must be unique. Use the template.")
    reader.fieldnames = header
    for count, raw in enumerate(reader, start=1):
        if count > max_rows:
            raise CsvShapeError(f"The file has more than {max_rows} rows.")
        if not any((v or "").strip() for v in raw.values() if isinstance(v, str)):
            continue  # blank line
        yield count + 1, raw


def template_csv(example_issuer: str, example_payer: str) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(TEMPLATE_COLUMNS)
    writer.writerow(
        [
            "INV-2026-0001",
            example_issuer,
            example_payer,
            "EUR",
            format_minor(1_250_000, 2),
            format_minor(1_250_000, 2),
            "2026-10-01",
            "2026-10-31",
        ]
    )
    return out.getvalue()
