"""MC-NET-01 component isolation, MC-ONB-02 settings, MC-APR-03 withdraw, MC-RSK-02 ring rule."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.core.ids import utcnow
from app.modules.audit.models import AuditEvent
from app.modules.demo.scenarios import MEMBERS
from app.modules.members.models import Member
from app.modules.netting import engine
from app.modules.netting.types import EngineInvariantError
from app.modules.risk.models import RiskDecision
from tests.api.conftest import Api
from tests.api.flows import (
    Factory,
    admin_run,
    approve_all,
    close,
    error_code,
    member_ids,
    ok,
    own_statement,
    ready,
    settle,
)

TAX = {m.code.lower(): m.tax_id for m in MEMBERS}


def invoice(api: Api, number: str, payer: str, issuer: str, amount: str) -> None:
    body = {
        "invoice_number": number,
        "issuer_tax_id": TAX[issuer],
        "payer_tax_id": TAX[payer],
        "currency": "EUR",
        "amount": amount,
        "issue_date": "2026-10-01",
        "due_date": "2026-10-31",
    }
    ok(api.post("/v1/invoices", json=body), 201)


def confirm_all(ops: Api) -> None:
    ok(ops.post("/v1/demo/simulate-confirmations", json={"confirm_pct": 100}))


def invoice_id(api: Api, number: str) -> str:
    items = ok(api.get("/v1/invoices"))["items"]
    return str(next(i["id"] for i in items if i["invoice_number"] == number))


def exclusion_reasons(api: Api, number: str) -> list[str]:
    detail = ok(api.get(f"/v1/invoices/{invoice_id(api, number)}"))
    return [e["reason"] for e in detail["exclusions"]]


def statement_invoices(statement: dict[str, Any]) -> set[str]:
    return {i["invoice_number"] for c in statement["counterparties"] for i in c["invoices"]}


def case_types(make_api: Factory) -> list[str]:
    cases = ok(make_api("compliance@wise.test").get("/v1/admin/cases"))["items"]
    return sorted(c["type"] for c in cases)


# --- MC-NET-01 ---------------------------------------------------------------------------


def test_a_failing_component_does_not_block_the_others(
    make_api: Factory, fresh_db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = member_ids(fresh_db)
    a, c, ops = make_api("finance@member-a.test"), make_api("finance@member-c.test"), None
    invoice(a, "CMP-AB", "a", "b", "1000.00")
    invoice(a, "CMP-BA", "b", "a", "400.00")
    invoice(c, "CMP-CD", "c", "d", "700.00")
    ops = make_api("ops@wise.test")
    confirm_all(ops)

    real = engine.cancel_cycles

    def flaky(edges: Any) -> Any:
        if any(ids["c"] in (e.payer, e.receiver) for e in edges):
            raise EngineInvariantError("MC-NET-02: injected failure")
        return real(edges)

    monkeypatch.setattr(engine, "cancel_cycles", flaky)
    run = close(ops)

    assert run["status"] == "AWAITING_APPROVAL"
    metrics = admin_run(ops, run["id"])["computations"][0]["metrics"]
    assert (metrics["component_count"], metrics["failed_components"]) == (2, 1)
    statement = own_statement(a, run["id"])
    assert statement is not None
    assert statement_invoices(statement) == {"CMP-AB", "CMP-BA"}
    assert own_statement(c, run["id"]) is None
    # The failed component's invoice goes back to the next window, shown as under review.
    assert {i["status"] for i in ok(c.get("/v1/invoices"))["items"]} == {"CONFIRMED"}
    assert exclusion_reasons(c, "CMP-CD") == ["UNDER_REVIEW"]
    assert case_types(make_api) == ["ENGINE_ALERT"]

    approve_all(make_api, run["id"], codes="ab")
    assert ok(settle(ops, run["id"]))["status"] == "COMMITTED"


# --- MC-ONB-02 ---------------------------------------------------------------------------


def test_member_admin_edits_settings_and_others_cannot(make_api: Factory, fresh_db: Engine) -> None:
    admin = make_api("admin@member-a.test")
    before = ok(admin.get("/v1/members/me"))
    assert {u["role"] for u in before["team"]} == {"MEMBER_ADMIN", "FINANCE_USER", "APPROVER"}

    after = ok(
        admin.patch(
            "/v1/members/me/settings",
            json={"payable_limit_minor": 2_500_000, "maker_checker_minor": None},
        )
    )
    assert after["payable_limit"] == {"amount_minor": 2_500_000, "currency": "EUR"}
    assert after["maker_checker_threshold"] is None
    assert after["settlement_currency"] == "EUR"  # omitted fields are kept

    for persona in ("finance", "approver"):
        api = make_api(f"{persona}@member-a.test")
        assert (
            api.patch("/v1/members/me/settings", json={"payable_limit_minor": 1}).status_code == 403
        )
    staff = make_api("ops@wise.test")
    assert (
        staff.patch("/v1/members/me/settings", json={"payable_limit_minor": 1}).status_code == 403
    )

    bad = admin.patch("/v1/members/me/settings", json={"settlement_currency": "XYZ"})
    assert (bad.status_code, error_code(bad)) == (422, "VALIDATION_FAILED")
    negative = admin.patch("/v1/members/me/settings", json={"payable_limit_minor": -1})
    assert negative.status_code == 422
    empty = admin.patch("/v1/members/me/settings", json={})
    assert error_code(empty) == "VALIDATION_FAILED"
    # Other members are untouched.
    b = ok(make_api("admin@member-b.test").get("/v1/members/me"))
    assert b["payable_limit"] != after["payable_limit"]

    with Session(fresh_db) as s:
        event = s.scalars(
            select(AuditEvent).where(AuditEvent.action == "member.settings_changed")
        ).one()
        assert event.reason_code == "SETTINGS_UPDATED"


def test_currency_change_waits_for_the_run_and_limits_exclude_over_limit_payers(
    make_api: Factory, fresh_db: Engine
) -> None:
    admin = make_api("admin@member-a.test")
    # Worked example: A's net payable is EUR 40,000. A 30,000 limit excludes A.
    ok(admin.patch("/v1/members/me/settings", json={"payable_limit_minor": 3_000_000}))
    ops = ready(make_api)
    run = close(ops)

    computation = admin_run(ops, run["id"])["computations"][0]
    assert computation["metrics"]["limit_restarts"] == 1
    finance = make_api("finance@member-a.test")
    assert own_statement(finance, run["id"]) is None
    assert exclusion_reasons(finance, "WX-2026-001") == ["LIMIT_EXCEEDED"]
    # The counterparty sees a neutral reason, never A's limit.
    assert exclusion_reasons(make_api("finance@member-b.test"), "WX-2026-001") == [
        "COUNTERPARTY_UNAVAILABLE"
    ]

    b_admin = make_api("admin@member-b.test")
    busy = b_admin.patch("/v1/members/me/settings", json={"settlement_currency": "USD"})
    assert (busy.status_code, error_code(busy)) == (409, "INVALID_STATE")
    # A has no invoices left in the run, so it may switch.
    switched = ok(admin.patch("/v1/members/me/settings", json={"settlement_currency": "USD"}))
    assert switched["settlement_currency"] == "USD"


# --- MC-APR-03 ---------------------------------------------------------------------------


def test_withdrawing_an_invoice_recomputes_and_keeps_unaffected_approvals(
    make_api: Factory,
) -> None:
    ops = ready(make_api)
    run = close(ops)
    e = make_api("finance@member-e.test")
    e_first = own_statement(e, run["id"])
    assert e_first is not None
    ok(
        e.post(
            f"/v1/statements/{e_first['statement_id']}/approvals",
            json={"decision": "APPROVE", "content_hash": e_first["content_hash"]},
        )
    )

    a = make_api("finance@member-a.test")
    before = own_statement(a, run["id"])
    assert before is not None and before["can_withdraw"]
    target = invoice_id(a, "WX-2026-001")  # A owes B 100k

    # Approvers can't withdraw; nobody can withdraw someone else's invoice.
    approver = make_api("approver@member-a.test")
    assert (
        approver.post(
            f"/v1/runs/{run['id']}/withdrawals", json={"invoice_ids": [target], "reason_code": "X"}
        ).status_code
        == 403
    )
    d = make_api("finance@member-d.test")
    stranger = d.post(
        f"/v1/runs/{run['id']}/withdrawals", json={"invoice_ids": [target], "reason_code": "X"}
    )
    assert stranger.status_code == 404
    blank = a.post(
        f"/v1/runs/{run['id']}/withdrawals", json={"invoice_ids": [target], "reason_code": " "}
    )
    assert blank.status_code == 422

    after = ok(
        a.post(
            f"/v1/runs/{run['id']}/withdrawals",
            json={"invoice_ids": [target], "reason_code": "PAID_OUTSIDE_MESH"},
        )
    )
    assert after["status"] == "AWAITING_APPROVAL" and after["current_attempt"] == 2
    assert admin_run(ops, run["id"])["computations"][-1]["trigger"] == "WITHDRAWN"

    a_now = own_statement(a, run["id"])
    assert a_now is not None and a_now["attempt"] == 2
    assert "WX-2026-001" not in statement_invoices(a_now)
    assert "WX-2026-001" in statement_invoices(before)
    assert {i["status"] for i in ok(a.get("/v1/invoices"))["items"] if i["id"] == target} == {
        "CONFIRMED"
    }
    assert exclusion_reasons(a, "WX-2026-001") == ["WITHDRAWN"]
    assert exclusion_reasons(make_api("finance@member-b.test"), "WX-2026-001") == [
        "COUNTERPARTY_UNAVAILABLE"
    ]
    # E's terms did not change, so its approval carried forward.
    e_now = own_statement(e, run["id"])
    assert e_now is not None and e_now["content_hash"] == e_first["content_hash"]
    assert e_now["approval"]["approval_count"] == 1

    # Withdrawing the same invoice again is refused: it's no longer on the statement.
    again = a.post(
        f"/v1/runs/{run['id']}/withdrawals", json={"invoice_ids": [target], "reason_code": "X"}
    )
    assert again.status_code == 404

    approve_all(make_api, run["id"])
    assert ok(settle(ops, run["id"]))["status"] == "COMMITTED"
    late_target = invoice_id(a, "WX-2026-003")
    late = a.post(
        f"/v1/runs/{run['id']}/withdrawals",
        json={"invoice_ids": [late_target], "reason_code": "X"},
    )
    assert (late.status_code, error_code(late)) == (409, "INVALID_STATE")


def test_withdrawals_share_the_recompute_cap(make_api: Factory) -> None:
    ops = ready(make_api)
    run = close(ops)
    a = make_api("finance@member-a.test")
    for number in ("WX-2026-001", "WX-2026-003"):
        ok(
            a.post(
                f"/v1/runs/{run['id']}/withdrawals",
                json={"invoice_ids": [invoice_id(a, number)], "reason_code": "X"},
            )
        )
    f = make_api("finance@member-f.test")
    last = ok(
        f.post(
            f"/v1/runs/{run['id']}/withdrawals",
            json={"invoice_ids": [invoice_id(f, "WX-2026-008")], "reason_code": "X"},
        )
    )
    assert last["status"] == "FALLBACK_GROSS"


# --- MC-RSK-02 ---------------------------------------------------------------------------


def test_established_members_never_trigger_the_ring_rule(make_api: Factory) -> None:
    ops = ready(make_api, "improvement_example")  # has an equal, round 3,000 EUR cycle
    run = close(ops)
    assert run["status"] == "AWAITING_APPROVAL"
    assert case_types(make_api) == []


def test_a_ring_of_new_members_is_held_for_review(make_api: Factory, fresh_db: Engine) -> None:
    ids = member_ids(fresh_db)
    with Session(fresh_db) as s, s.begin():
        s.execute(
            update(Member)
            .where(Member.id.in_([ids["c"], ids["d"], ids["e"]]))
            .values(created_at=utcnow() - timedelta(days=10))
        )
    c, d, a = (make_api(f"finance@member-{x}.test") for x in "cda")
    invoice(c, "RING-1", "c", "d", "5000.00")
    invoice(d, "RING-2", "d", "e", "5000.00")
    invoice(c, "RING-3", "e", "c", "5000.00")
    invoice(c, "NOT-ROUND", "c", "d", "5000.10")
    invoice(a, "PAIR-1", "a", "b", "2000.00")
    invoice(a, "PAIR-2", "b", "a", "2000.00")  # equal and round, but A and B are established
    ops = make_api("ops@wise.test")
    confirm_all(ops)
    run = close(ops)

    assert run["status"] == "AWAITING_APPROVAL"
    for number in ("RING-1", "RING-2", "RING-3"):
        assert exclusion_reasons(c if number != "RING-2" else d, number) == ["UNDER_REVIEW"]
    c_statement = own_statement(c, run["id"])
    assert c_statement is not None
    assert statement_invoices(c_statement) == {"NOT-ROUND"}
    a_statement = own_statement(a, run["id"])
    assert a_statement is not None
    assert statement_invoices(a_statement) == {"PAIR-1", "PAIR-2"}
    assert case_types(make_api) == ["RING"]
    with Session(fresh_db) as s:
        decisions = s.scalars(select(RiskDecision).where(RiskDecision.rule == "RING")).all()
        assert sorted(x.decision for x in decisions) == ["HOLD_FOR_REVIEW"] * 3
        assert {x.reasons["amount_minor"] for x in decisions} == {500_000}
