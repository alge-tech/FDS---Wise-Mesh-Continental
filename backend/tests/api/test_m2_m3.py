from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.hashing import hash_canonical
from app.modules.members.models import Member
from app.modules.risk.models import SanctionsEntry
from tests.api.conftest import Api

Factory = Callable[..., Api]


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def ready(make_api: Factory) -> Api:
    ops = make_api("ops@wise.test")
    assert ok(ops.post("/v1/demo/scenarios/worked_example"))["created"] == 8
    assert (
        ok(ops.post("/v1/demo/simulate-confirmations", json={"confirm_pct": 100}))["confirmed"] == 8
    )
    return ops


def close(ops: Api) -> dict[str, Any]:
    return ok(ops.post("/v1/admin/windows/current/close", json={"reason_code": "DEMO_CLOSE"}))  # type: ignore[no-any-return]


def own_statement(api: Api, run_id: str) -> dict[str, Any]:
    run = ok(api.get(f"/v1/runs/{run_id}"))
    return ok(api.get(f"/v1/statements/{run['statement_id']}"))  # type: ignore[no-any-return]


ENVELOPE = {
    "statement_id",
    "run_id",
    "attempt",
    "member_id",
    "approval",
    "can_withdraw",
    "content_hash",
    "run_status",
    "current",
    "current_statement_id",
    "issued_at",
}


def economic(statement: dict[str, Any]) -> dict[str, Any]:
    """The hashed part of a statement: everything but IDs, attempt, approval and reference."""
    content = {k: v for k, v in statement.items() if k not in ENVELOPE}
    content["instruction"] = {k: v for k, v in content["instruction"].items() if k != "reference"}
    return content


def answer(api: Api, s: dict[str, Any], decision: str = "APPROVE") -> Any:
    return api.post(
        f"/v1/statements/{s['statement_id']}/approvals",
        json={"decision": decision, "content_hash": s["content_hash"]},
    )


def test_worked_example_m2_and_m3_gates(make_api: Factory) -> None:
    ops = ready(make_api)
    assert ok(ops.get("/v1/windows/current"))["eligible_count"] == 8
    initial_window = ok(ops.get("/v1/windows/current"))["id"]
    run = close(ops)
    assert run["status"] == "AWAITING_APPROVAL"
    metrics = run["computations"][0]["metrics"]
    assert metrics["transfer_count"] == 3
    assert metrics["gross_minor"] == {"EUR": 45_000_000}
    assert metrics["net_minor"] == {"EUR": 8_000_000}
    assert ok(ops.get("/v1/windows/current"))["id"] != initial_window
    for code in "abcdef":
        member = make_api(f"finance@member-{code}.test")
        statement = own_statement(member, run["id"])
        assert statement["content_hash"] == "sha256:" + hash_canonical(economic(statement))
        assert statement["instruction"]["counterparty"] == "Mesh settlement"
        assert statement["instruction"]["reference"].startswith("MESH-")
        assert statement["attempt"] == 1
        if code == "a":
            assert statement["net"] == {"amount_minor": -4_000_000, "currency": "EUR"}
            assert statement["gross_payable"] == {"amount_minor": 10_000_000, "currency": "EUR"}
            assert statement["gross_receivable"] == {"amount_minor": 6_000_000, "currency": "EUR"}
            assert statement["instruction"]["type"] == "DEBIT"
            # PRD sample: the A->B invoice is 100k outstanding, 60k cancelled, 40k residual.
            [ab] = [
                i
                for c in statement["counterparties"]
                for i in c["invoices"]
                if i["direction"] == "PAYABLE"
            ]
            assert (
                ab["outstanding"]["amount_minor"],
                ab["cancelled"]["amount_minor"],
                ab["residual"]["amount_minor"],
            ) == (10_000_000, 6_000_000, 4_000_000)
            assert sum(len(c["invoices"]) for c in statement["counterparties"]) == 2
        ok(answer(member, statement))
    final = ok(ops.get(f"/v1/admin/runs/{run['id']}"))
    assert final["status"] == "APPROVED"


def test_ingestion_dispute_correction_and_stale_version(make_api: Factory) -> None:
    a = make_api("finance@member-a.test")
    b = make_api("finance@member-b.test")
    body = {
        "invoice_number": "INV-ONE",
        "issuer_tax_id": "DE811000001",
        "payer_tax_id": "LV400000002",
        "currency": "EUR",
        "amount": "125.00",
        "issue_date": "2026-10-01",
        "due_date": "2026-10-31",
    }
    invoice = ok(a.post("/v1/invoices", json=body, key="create-one"), 201)
    assert ok(a.post("/v1/invoices", json=body, key="create-one"), 201) == invoice
    assert a.post("/v1/invoices", json=body).json()["error"]["code"] == "DUPLICATE_INVOICE"
    assert len(ok(b.get("/v1/confirmations"))["items"]) == 1
    ok(
        b.post(
            f"/v1/invoices/{invoice['id']}/confirmations",
            json={"decision": "DISPUTE", "version": 1, "reason_code": "WRONG_AMOUNT"},
        )
    )
    assert ok(b.get("/v1/windows/current"))["exclusions"][0]["reason"] == "DISPUTED"
    amended = ok(
        a.post(
            f"/v1/invoices/{invoice['id']}/confirmations",
            json={
                "decision": "CORRECT",
                "version": 1,
                "corrected_fields": {"amount": "150.00", "outstanding": "150.00"},
            },
        )
    )
    assert amended["current_version"] == 2
    stale = b.post(
        f"/v1/invoices/{invoice['id']}/confirmations", json={"decision": "CONFIRM", "version": 1}
    )
    assert stale.status_code == 409
    for api in (a, b):
        ok(
            api.post(
                f"/v1/invoices/{invoice['id']}/confirmations",
                json={"decision": "CONFIRM", "version": 2},
            )
        )
    assert ok(a.get("/v1/windows/current"))["eligible_count"] == 1
    detail = ok(a.get(f"/v1/invoices/{invoice['id']}"))
    assert len(detail["versions"]) == 2
    assert len(detail["confirmations"]) == 4


def test_csv_validation_matching_and_roles(make_api: Factory) -> None:
    a = make_api("finance@member-a.test")
    header = (
        "invoice_number,issuer_tax_id,payer_tax_id,currency,amount,"
        "outstanding,issue_date,due_date\n"
    )
    rows = (
        "CSV1,DE811000001,LV-40002,EUR,100.00,,2026-10-01,2026-10-31\n"
        "CSV2,DE811000001,NL800000008,EUR,10.00,,2026-10-01,2026-10-31\n"
        "CSV3,DE811000001,LV400000002,EUR,1e2,,2026-10-01,2026-10-31\n"
    )
    response = ok(
        a.post("/v1/invoices/uploads", content=header + rows, headers={"Content-Type": "text/csv"})
    )
    assert len(response["items"]) == 2
    assert response["errors"][0]["row"] == 4
    assert response["items"][1]["status"] == "UNMATCHED"
    assert len(ok(a.get("/v1/counterparties"))["items"]) == 2
    assert (
        make_api("approver@member-a.test").post("/v1/invoices/uploads", content=header).status_code
        == 403
    )
    assert ok(a.get("/v1/invoices?limit=1"))["next_cursor"] is not None
    assert a.post("/v1/invoices/uploads", content="bad\n").status_code == 422


def test_privacy_and_stale_statement(make_api: Factory) -> None:
    ops = ready(make_api)
    run = close(ops)
    a, b = make_api("finance@member-a.test"), make_api("finance@member-b.test")
    s = own_statement(a, run["id"])
    assert b.get(f"/v1/statements/{s['statement_id']}").status_code == 404
    i = next(i for i in ok(a.get("/v1/invoices"))["items"] if "Aurora" not in i["counterparty"])
    assert make_api("finance@member-e.test").get(f"/v1/invoices/{i['id']}").status_code == 404
    stale = a.post(
        f"/v1/statements/{s['statement_id']}/approvals",
        json={"decision": "APPROVE", "content_hash": "sha256:" + "0" * 64},
    )
    assert stale.json()["error"]["code"] == "STATEMENT_CHANGED"
    assert ok(a.get(f"/v1/runs/{run['id']}"))["computations"] == []


def test_reject_recomputes_and_third_exclusion_falls_back(make_api: Factory) -> None:
    ops = ready(make_api)
    run = close(ops)
    for attempt, code in enumerate("abc", start=1):
        api = make_api(f"admin@member-{code}.test")
        statement = own_statement(api, run["id"])
        ok(answer(api, statement, "REJECT"))
        updated = ok(ops.get(f"/v1/admin/runs/{run['id']}"))
        if attempt < 3:
            assert updated["current_attempt"] == attempt + 1
            assert updated["status"] == "AWAITING_APPROVAL"
            assert answer(api, statement).json()["error"]["code"] == "STATEMENT_CHANGED"
        else:
            assert updated["status"] == "FALLBACK_GROSS"
    assert all(
        i["status"] == "CONFIRMED"
        for i in ok(make_api("finance@member-f.test").get("/v1/invoices"))["items"]
    )


def test_global_and_member_kill_switches(make_api: Factory) -> None:
    ops = ready(make_api)
    ok(
        ops.put(
            "/v1/admin/kill-switches", json={"scope": "GLOBAL", "enabled": True, "reason": "PAUSE"}
        )
    )
    assert (
        ops.post("/v1/admin/windows/current/close", json={"reason_code": "CLOSE"}).json()["error"][
            "code"
        ]
        == "KILL_SWITCH_ON"
    )
    ok(
        ops.put(
            "/v1/admin/kill-switches",
            json={"scope": "GLOBAL", "enabled": False, "reason": "RESUME"},
        )
    )
    a = make_api("finance@member-a.test")
    member_id = ok(a.get("/v1/me"))["member"]["member_id"]
    ok(
        ops.put(
            "/v1/admin/kill-switches",
            json={"scope": "MEMBER", "member_id": member_id, "enabled": True, "reason": "PAUSE_A"},
        )
    )
    b = make_api("finance@member-b.test")
    assert ok(b.get("/v1/windows/current"))["exclusions"][0]["reason"] == "COUNTERPARTY_UNAVAILABLE"
    assert close(ops)["computations"][0]["metrics"]["invoice_count"] == 6


def test_sanctions_screening_releases_and_opens_case(make_api: Factory, fresh_db: Any) -> None:
    ops = ready(make_api)
    with Session(fresh_db) as session, session.begin():
        session.add(
            SanctionsEntry(
                name="Aurora Components GmbH", country="DE", tax_id="DE811000001", source="TEST"
            )
        )
    run = close(ops)
    assert run["computations"][0]["metrics"]["invoice_count"] == 6
    a = make_api("finance@member-a.test")
    assert all(i["status"] == "CONFIRMED" for i in ok(a.get("/v1/invoices"))["items"])
    assert ok(a.get(f"/v1/runs/{run['id']}"))["statement_id"] is None


def test_above_threshold_role_and_distinct_approvers(make_api: Factory, fresh_db: Any) -> None:
    ops = ready(make_api)
    with Session(fresh_db) as session, session.begin():
        member = session.scalar(select(Member).where(Member.display_name == "Member A"))
        assert member
        member.maker_checker_minor = 1
    run = close(ops)
    finance = make_api("finance@member-a.test")
    s = own_statement(finance, run["id"])
    assert s["approval"]["required_approvers"] == 2
    assert answer(finance, s).status_code == 403
    admin = make_api("admin@member-a.test")
    ok(answer(admin, s))
    assert answer(admin, s).json()["error"]["code"] == "ALREADY_APPROVED"
    ok(answer(make_api("approver@member-a.test"), s))


def test_unchanged_statement_approval_is_carried_forward(make_api: Factory) -> None:
    ops = ready(make_api)
    run = close(ops)
    d = make_api("finance@member-d.test")
    old = own_statement(d, run["id"])
    ok(answer(d, old))
    a = make_api("finance@member-a.test")
    ok(answer(a, own_statement(a, run["id"]), "REJECT"))
    new = own_statement(d, run["id"])
    assert new["statement_id"] != old["statement_id"]
    assert new["attempt"] == 2
    assert new["content_hash"] == old["content_hash"]
    assert new["approval"]["approval_count"] == 1
    own_run = ok(d.get(f"/v1/runs/{run['id']}"))
    assert own_run["approvals"][0]["method"] == "CARRIED_FORWARD"


def test_generator_repeats_and_demo_gate(make_api: Factory, monkeypatch: Any) -> None:
    from app.core.config import get_settings

    ops = make_api("ops@wise.test")
    body = {"members": 8, "invoices": 20, "seed": 47, "cycle_density": 100}
    assert ok(ops.post("/v1/demo/generate", json=body))["created"] == 20
    assert ok(ops.post("/v1/demo/generate", json=body))["created"] == 0
    assert ok(ops.post("/v1/demo/simulate-confirmations", json={}))["confirmed"] == 20
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    assert ops.post("/v1/demo/generate", json=body).json()["error"]["code"] == "DEMO_MODE_OFF"
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()


def test_run_resource_scoping_and_empty_window(make_api: Factory) -> None:
    ops = make_api("ops@wise.test")
    assert (
        ops.post("/v1/admin/windows/current/close", json={"reason_code": "EMPTY"}).status_code
        == 409
    )
    a = make_api("finance@member-a.test")
    body = {
        "invoice_number": "SCOPED",
        "issuer_tax_id": "DE811000001",
        "payer_tax_id": "LV400000002",
        "currency": "EUR",
        "amount": "10.00",
        "issue_date": "2026-10-01",
        "due_date": "2026-10-31",
    }
    invoice = ok(a.post("/v1/invoices", json=body), 201)
    ok(ops.post("/v1/demo/simulate-confirmations", json={}))
    run = close(ops)
    c = make_api("finance@member-c.test")
    assert c.get(f"/v1/runs/{run['id']}").status_code == 404
    assert ok(c.get("/v1/runs"))["items"] == []
    assert c.get(f"/v1/invoices/{invoice['id']}").status_code == 404
    assert a.get(f"/v1/admin/runs/{run['id']}").status_code == 403


def test_alias_identity_cannot_bypass_duplicate_fingerprint(make_api: Factory) -> None:
    a = make_api("finance@member-a.test")
    body = {
        "invoice_number": "ALIAS",
        "issuer_tax_id": "DE811000001",
        "payer_tax_id": "LV400000002",
        "currency": "EUR",
        "amount": "10.00",
        "issue_date": "2026-10-01",
        "due_date": "2026-10-31",
    }
    ok(a.post("/v1/invoices", json=body), 201)
    body["payer_tax_id"] = "LV-40002"
    duplicate = a.post("/v1/invoices", json=body)
    assert duplicate.json()["error"]["code"] == "DUPLICATE_INVOICE"


def test_ingest_large_amount_returns_validation_error(make_api: Factory) -> None:
    a = make_api("finance@member-a.test")
    body = {
        "invoice_number": "TOO_BIG",
        "issuer_tax_id": "DE811000001",
        "payer_tax_id": "LV400000002",
        "currency": "EUR",
        "amount": "9" * 100,
        "issue_date": "2026-10-01",
        "due_date": "2026-10-31",
    }
    assert a.post("/v1/invoices", json=body).status_code == 422


def test_completed_statement_disallows_extra_approvals(make_api: Factory) -> None:
    ops = ready(make_api)
    run = close(ops)
    a = make_api("finance@member-a.test")
    statement = own_statement(a, run["id"])
    ok(answer(a, statement))
    admin = make_api("admin@member-a.test")
    assert not own_statement(admin, run["id"])["approval"]["can_approve"]
    assert answer(admin, statement).status_code == 409
