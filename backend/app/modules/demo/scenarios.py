"""Demo datasets. Pure data, shared by the seed, the scenario endpoint and the tests."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedMember:
    code: str  # "A" .. "F"
    display_name: str
    legal_name: str
    tax_id: str
    registration_no: str
    country: str
    settlement_currency: str
    payable_limit_major: int | None
    maker_checker_major: int | None
    opening_balances_major: dict[str, int]


@dataclass(frozen=True)
class ScenarioInvoice:
    invoice_number: str
    payer: str  # member code
    issuer: str  # member code (receiver)
    currency: str
    amount_major: int
    issue_date: str
    due_date: str


MEMBERS: tuple[SeedMember, ...] = (
    SeedMember(
        "A",
        "Member A",
        "Aurora Components GmbH",
        "DE811000001",
        "HRB-10001",
        "DE",
        "EUR",
        None,
        50_000,
        {"EUR": 150_000, "USD": 20_000},
    ),
    SeedMember(
        "B",
        "Member B",
        "Baltic Freight SIA",
        "LV400000002",
        "LV-40002",
        "LV",
        "EUR",
        None,
        50_000,
        {"EUR": 120_000, "USD": 10_000},
    ),
    SeedMember(
        "C",
        "Member C",
        "Castell Textiles SL",
        "ESB0000003",
        "ES-B0003",
        "ES",
        "EUR",
        None,
        50_000,
        {"EUR": 120_000, "GBP": 10_000, "USD": 10_000},
    ),
    SeedMember(
        "D",
        "Member D",
        "Danube Agro Kft",
        "HU10000004",
        "HU-01-09-000004",
        "HU",
        "EUR",
        None,
        50_000,
        {"EUR": 100_000, "HUF": 5_000_000, "USD": 10_000},
    ),
    SeedMember(
        "E",
        "Member E",
        "Eastwind Electronics Ltd",
        "GB000000005",
        "GB-00000005",
        "GB",
        "EUR",
        None,
        50_000,
        {"EUR": 100_000, "GBP": 20_000, "USD": 10_000},
    ),
    SeedMember(
        "F",
        "Member F",
        "Fjord Logistics AS",
        "NO900000006",
        "NO-900000006",
        "NO",
        "EUR",
        None,
        50_000,
        {"EUR": 80_000, "USD": 30_000},
    ),
)

# Legal entity that is on the mock sanctions list; it becomes a member only in the
# sanctions demo, so the worked example stays clean.
SANCTIONED_ENTITY = {
    "legal_name": "Gorgon Trading FZE",
    "tax_id": "AE700000007",
    "registration_no": "AE-7007",
    "country": "AE",
}

# A seeded legal entity that is not a member: invoices to it stay UNMATCHED.
NON_MEMBER_ENTITY = {
    "legal_name": "Harbour Supplies BV",
    "tax_id": "NL800000008",
    "registration_no": "NL-8008",
    "country": "NL",
}

# MC-NET-08. 8 invoices worth 450k become 3 transfers worth 80k (A, C and E pay F).
# Cycle A->B->C->A cancels 60k and cycle D->E->F->D cancels 30k: 270k cancelled, 180k
# residual on invoices, 80k actually moved. Nets: A -40, B 0, C -30, D 0, E -10, F +80.
WORKED_EXAMPLE: tuple[ScenarioInvoice, ...] = (
    ScenarioInvoice("WX-2026-001", "A", "B", "EUR", 100_000, "2026-09-01", "2026-10-31"),
    ScenarioInvoice("WX-2026-002", "B", "C", "EUR", 80_000, "2026-09-02", "2026-10-31"),
    ScenarioInvoice("WX-2026-003", "C", "A", "EUR", 60_000, "2026-09-03", "2026-10-31"),
    ScenarioInvoice("WX-2026-004", "B", "D", "EUR", 20_000, "2026-09-04", "2026-10-31"),
    ScenarioInvoice("WX-2026-005", "C", "F", "EUR", 50_000, "2026-09-05", "2026-10-31"),
    ScenarioInvoice("WX-2026-006", "D", "E", "EUR", 50_000, "2026-09-06", "2026-10-31"),
    ScenarioInvoice("WX-2026-007", "E", "F", "EUR", 60_000, "2026-09-07", "2026-10-31"),
    ScenarioInvoice("WX-2026-008", "F", "D", "EUR", 30_000, "2026-09-08", "2026-10-31"),
)

# MC-NET-05. Nets A +9k, B +8k, C -7k, D -5k, E -4k, F -1k. Greedy needs 5 transfers;
# settling the zero-sum groups {A, D, E} and {B, C, F} on their own needs 4.
IMPROVEMENT_EXAMPLE: tuple[ScenarioInvoice, ...] = (
    ScenarioInvoice("IX-2026-001", "D", "A", "EUR", 5_000, "2026-09-10", "2026-10-31"),
    ScenarioInvoice("IX-2026-002", "E", "A", "EUR", 4_000, "2026-09-10", "2026-10-31"),
    ScenarioInvoice("IX-2026-003", "C", "B", "EUR", 7_000, "2026-09-11", "2026-10-31"),
    ScenarioInvoice("IX-2026-004", "F", "B", "EUR", 1_000, "2026-09-11", "2026-10-31"),
    ScenarioInvoice("IX-2026-005", "A", "C", "EUR", 3_000, "2026-09-12", "2026-10-31"),
    ScenarioInvoice("IX-2026-006", "C", "E", "EUR", 3_000, "2026-09-12", "2026-10-31"),
    ScenarioInvoice("IX-2026-007", "E", "A", "EUR", 3_000, "2026-09-12", "2026-10-31"),
)

SCENARIOS = {"worked_example": WORKED_EXAMPLE, "improvement_example": IMPROVEMENT_EXAMPLE}
