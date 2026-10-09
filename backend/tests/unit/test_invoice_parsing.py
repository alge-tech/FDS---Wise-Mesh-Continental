"""MC-ING-01 / MC-ING-04: CSV and row validation, fingerprints. Pure, no database."""

from datetime import date

import pytest

from app.modules.invoices.parsing import (
    TEMPLATE_COLUMNS,
    CsvShapeError,
    ParsedInvoice,
    RowError,
    fingerprint,
    read_csv,
    template_csv,
    validate_row,
)

EXPONENTS = {"EUR": 2, "USD": 2, "HUF": 2}
GOOD = {
    "invoice_number": "INV-1",
    "issuer_tax_id": "DE 123-456.789",
    "payer_tax_id": "fr999",
    "currency": "eur",
    "amount": "1250.50",
    "outstanding": "1000",
    "issue_date": "2026-10-01",
    "due_date": "2026-10-31",
}


def errors_of(raw: dict[str, str | None]) -> dict[str, str]:
    result = validate_row(raw, 2, EXPONENTS)
    assert isinstance(result, list), result
    assert all(isinstance(e, RowError) and e.row == 2 for e in result)
    return {e.field: e.reason for e in result}


def test_valid_row_is_normalised_to_minor_units() -> None:
    parsed = validate_row(GOOD, 2, EXPONENTS)
    assert parsed == ParsedInvoice(
        row=2,
        invoice_number="INV-1",
        issuer_tax_id="DE123456789",
        payer_tax_id="FR999",
        currency="EUR",
        amount_minor=125050,
        outstanding_minor=100000,
        issue_date=date(2026, 10, 1),
        due_date=date(2026, 10, 31),
    )


def test_blank_outstanding_defaults_to_the_amount() -> None:
    parsed = validate_row({**GOOD, "outstanding": " "}, 2, EXPONENTS)
    assert isinstance(parsed, ParsedInvoice)
    assert parsed.outstanding_minor == parsed.amount_minor == 125050


def test_every_field_error_is_reported_not_just_the_first() -> None:
    errors = errors_of(
        {
            "invoice_number": "",
            "issuer_tax_id": None,
            "payer_tax_id": "",
            "currency": "XYZ",
            "amount": "1",
            "issue_date": "01/10/2026",
            "due_date": "2026-02-30",
        }
    )
    assert set(errors) == {
        "invoice_number",
        "issuer_tax_id",
        "payer_tax_id",
        "currency",
        "issue_date",
        "due_date",
    }
    assert "EUR, HUF, USD" in errors["currency"]
    assert "YYYY-MM-DD" in errors["issue_date"]
    assert errors["due_date"] == "is not a valid date"


@pytest.mark.parametrize(
    ("override", "field", "reason_part"),
    [
        ({"amount": "1e3"}, "amount", "plain decimal"),
        ({"amount": "-5"}, "amount", "negative"),
        ({"amount": "12.345"}, "amount", "decimal places"),
        ({"amount": "0"}, "amount", "greater than zero"),
        ({"amount": "9" * 25}, "amount", "too large"),
        ({"amount": "99999999999999999999"}, "amount", "too large"),
        ({"outstanding": "0.00"}, "outstanding", "greater than zero"),
        ({"outstanding": "1250.51"}, "outstanding", "must not exceed"),
        ({"outstanding": "1,000"}, "outstanding", "plain decimal"),
        ({"payer_tax_id": "de-123 456 789"}, "payer_tax_id", "differ from the issuer"),
        ({"invoice_number": "X" * 65}, "invoice_number", "longer than 64"),
        ({"due_date": "2026-09-30"}, "due_date", "before the issue date"),
    ],
)
def test_row_rejections(override: dict[str, str], field: str, reason_part: str) -> None:
    errors = errors_of({**GOOD, **override})
    assert field in errors
    assert reason_part in errors[field]


def test_fingerprint_ignores_formatting_but_not_identity() -> None:
    base = fingerprint("DE123", "FR9", "inv-1", date(2026, 10, 1), "EUR", 100)
    assert base == fingerprint("de 1-23", "fr.9", "  INV-1 ", date(2026, 10, 1), "eur", 100)
    assert len(base) == 64
    for changed in (
        fingerprint("DE124", "FR9", "INV-1", date(2026, 10, 1), "EUR", 100),
        fingerprint("DE123", "FR8", "INV-1", date(2026, 10, 1), "EUR", 100),
        fingerprint("DE123", "FR9", "INV-2", date(2026, 10, 1), "EUR", 100),
        fingerprint("DE123", "FR9", "INV-1", date(2026, 10, 2), "EUR", 100),
        fingerprint("DE123", "FR9", "INV-1", date(2026, 10, 1), "USD", 100),
        fingerprint("DE123", "FR9", "INV-1", date(2026, 10, 1), "EUR", 101),
    ):
        assert changed != base


def test_parsed_invoice_fingerprint_uses_the_normalised_fields() -> None:
    parsed = validate_row(GOOD, 2, EXPONENTS)
    assert isinstance(parsed, ParsedInvoice)
    assert parsed.fingerprint == fingerprint(
        "DE123456789", "FR999", "INV-1", date(2026, 10, 1), "EUR", 125050
    )


def csv_bytes(*rows: str, header: str = ",".join(TEMPLATE_COLUMNS)) -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode()


def test_read_csv_numbers_rows_from_two_and_skips_blank_lines() -> None:
    content = csv_bytes(
        "A,DE1,FR1,EUR,1,,2026-10-01,2026-10-31",
        ",,,,,,,",
        "B,DE1,FR1,EUR,2,,2026-10-01,2026-10-31",
    )
    rows = list(read_csv(content, max_rows=10))
    assert [(n, r["invoice_number"]) for n, r in rows] == [(2, "A"), (4, "B")]


def test_read_csv_accepts_a_bom_and_padded_headers() -> None:
    header = "﻿" + ", ".join(TEMPLATE_COLUMNS)
    content = csv_bytes("A,DE1,FR1,EUR,1,,2026-10-01,2026-10-31", header=header)
    [(_, row)] = list(read_csv(content, max_rows=10))
    assert row["invoice_number"] == "A"
    assert row["due_date"] == "2026-10-31"


def test_read_csv_rejects_missing_and_duplicate_columns() -> None:
    with pytest.raises(CsvShapeError, match="Missing columns: due_date"):
        list(read_csv(csv_bytes(header=",".join(TEMPLATE_COLUMNS[:-1])), max_rows=10))
    with pytest.raises(CsvShapeError, match="unique"):
        list(read_csv(csv_bytes(header=",".join((*TEMPLATE_COLUMNS, "amount"))), max_rows=10))


def test_read_csv_rejects_non_utf8() -> None:
    with pytest.raises(CsvShapeError, match="UTF-8"):
        list(read_csv(b"invoice_number\n\xff\xfe\xfa\n", max_rows=10))


def test_read_csv_enforces_the_row_cap() -> None:
    row = "A,DE1,FR1,EUR,1,,2026-10-01,2026-10-31"
    assert len(list(read_csv(csv_bytes(row, row), max_rows=2))) == 2
    with pytest.raises(CsvShapeError, match="more than 2 rows"):
        list(read_csv(csv_bytes(row, row, row), max_rows=2))


def test_template_round_trips_through_the_parser() -> None:
    content = template_csv("DE111", "FR222").encode()
    [(row_no, raw)] = list(read_csv(content, max_rows=10))
    parsed = validate_row(raw, row_no, EXPONENTS)
    assert isinstance(parsed, ParsedInvoice)
    assert (parsed.amount_minor, parsed.outstanding_minor) == (1_250_000, 1_250_000)
    assert (parsed.issuer_tax_id, parsed.payer_tax_id) == ("DE111", "FR222")
