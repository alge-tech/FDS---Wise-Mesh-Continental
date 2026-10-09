"""M4 gate: clearing is zero after commit, and a funding failure re-computes.

Also: holds, outcomes, idempotent settle, abort, kill switch, input tampering, prepare-time
screening, FX locks, expired approvals, the recompute cap, savings and the ledger check.
"""

import json
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.orm import Session

from app.core.enums import JournalKind, LedgerAccountType
from app.core.ids import utcnow
from app.events.worker import drain
from app.modules.audit.models import AuditEvent
from app.modules.fx.models import FxLock
from app.modules.ledger import service as ledger
from app.modules.ledger.models import JournalEntry
from app.modules.ledger.postings import AccountRef, PostingLine
from app.modules.members.models import Member
from app.modules.risk.models import SanctionsEntry
from app.modules.settlement.models import Hold
from tests.api.flows import (
    CODES,
    Factory,
    admin_run,
    approve_all,
    balances,
    close,
    error_code,
    member_ids,
    ok,
    own_statement,
    ready,
    settle,
)


def approved_run(make_api: Factory) -> tuple[Any, dict[str, Any]]:
    ops = ready(make_api)
    run = close(ops)
    approve_all(make_api, run["id"])
    assert admin_run(ops, run["id"])["status"] == "APPROVED"
    return ops, run


def commit_entries(engine: Engine, run_id: str) -> int:
    with Session(engine) as s:
        return int(
            s.scalar(
                select(func.count())
                .select_from(JournalEntry)
                .where(
                    JournalEntry.run_id == run_id,  # type: ignore[arg-type]
                    JournalEntry.kind == JournalKind.COMMIT,
                )
            )
            or 0
        )


def test_m4_gate_worked_example_settles_and_clearing_is_zero(
    make_api: Factory, fresh_db: Engine
) -> None:
    ops, run = approved_run(make_api)
    members = {c: make_api(f"finance@member-{c}.test") for c in CODES}
    before = {c: balances(api)["EUR"][0] for c, api in members.items()}
    statements = {c: own_statement(api, run["id"]) for c, api in members.items()}

    done = ok(settle(ops, run["id"]))
    assert done["status"] == "COMMITTED"
    assert done["finished_at"] is not None
    detail = done["settlement_detail"]
    assert detail["clearing"] and all(c["balance_minor"] == 0 for c in detail["clearing"])
    assert detail["holds"] and all(h["status"] == "CONSUMED" for h in detail["holds"])
    assert {t["status"] for t in detail["transfers"]} == {"SETTLED"}
    assert sum(t["amount_minor"] for t in detail["transfers"]) == 8_000_000
    assert detail["commit_entry_seq"] is not None
    assert [j["status"] for j in detail["jobs"] if j["member_id"] is None] == ["DONE", "DONE"]

    check = ok(ops.get("/v1/admin/ledger/check"))
    assert check["ok"] and check["chain_ok"] and check["clearing_ok"]
    assert check["active_holds"] == 0

    fees = 0
    for code, api in members.items():
        s = statements[code]
        assert s is not None
        fee = s["fee"]["amount_minor"]
        fees += fee
        # G2: each member moved exactly its net position, fees aside.
        assert balances(api)["EUR"] == (
            before[code] + s["net"]["amount_minor"] - fee,
            0,
        )
        mine = ok(api.get(f"/v1/runs/{run['id']}"))["settlement"]
        assert mine["status"] == "SETTLED"
        assert mine["counterparty"] == "Mesh settlement"
        assert all(line["counterparty"] == "Mesh settlement" for line in mine["ledger"])
        assert mine["instruction"] == s["instruction"]["type"]
    assert fees > 0

    a = members["a"]
    invoices = ok(a.get("/v1/invoices"))["items"]
    assert {i["status"] for i in invoices} == {"SETTLED_BY_NETTING", "SETTLED_BY_TRANSFER"}
    netted = next(i for i in invoices if i["invoice_number"] == "WX-2026-003")
    assert netted["status"] == "SETTLED_BY_NETTING"
    outcome = ok(a.get(f"/v1/invoices/{netted['id']}"))["outcomes"]
    assert outcome == [
        {
            "run_id": run["id"],
            "outcome": "SETTLED_BY_NETTING",
            "cancelled_minor": 6_000_000,
            "residual_minor": 0,
        }
    ]
    mine = ok(a.get(f"/v1/runs/{run['id']}"))["settlement"]
    assert (mine["settled_by_netting"], mine["settled_by_transfer"]) == (1, 1)

    # MC-PRV-02: a member's run view names no other member.
    ids = member_ids(fresh_db)
    raw = json.dumps(ok(a.get(f"/v1/runs/{run['id']}")))
    assert not any(str(ids[c]) in raw for c in "bcdef")


def test_settle_is_idempotent_and_repeats_have_no_effect(
    make_api: Factory, fresh_db: Engine
) -> None:
    ops, run = approved_run(make_api)
    first = ok(settle(ops, run["id"], key="settle-1"))
    assert ok(settle(ops, run["id"], key="settle-1")) == first
    a = make_api("finance@member-a.test")
    after = balances(a)
    again = ok(settle(ops, run["id"], key="settle-2"))
    assert again["status"] == "COMMITTED"
    assert commit_entries(fresh_db, run["id"]) == 1
    assert balances(a) == after


def test_m4_gate_funding_failure_recomputes_new_statements(
    make_api: Factory, fresh_db: Engine
) -> None:
    ops, run = approved_run(make_api)
    ids = member_ids(fresh_db)
    c = make_api("finance@member-c.test")
    old = own_statement(c, run["id"])
    blocked = ok(
        ops.post(
            "/v1/demo/funding-failure", json={"member_id": str(ids["c"]), "unable_to_fund": True}
        )
    )
    assert blocked["funding_blocked"] is True

    recomputed = ok(settle(ops, run["id"]))
    assert recomputed["status"] == "AWAITING_APPROVAL"
    assert recomputed["current_attempt"] == 2
    assert recomputed["computations"][-1]["trigger"] == "FUNDING_FAILED"
    assert recomputed["settlement_detail"]["holds"] == []
    prepare = next(j for j in recomputed["settlement_detail"]["jobs"] if j["step"] == "PREPARE")
    assert prepare["result"]["outcome"] == "RECOMPUTED"
    assert own_statement(c, run["id"]) is None
    assert {i["status"] for i in ok(c.get("/v1/invoices"))["items"]} == {"CONFIRMED"}
    assert old is not None
    detail = ok(c.get(f"/v1/invoices/{old['counterparties'][0]['invoices'][0]['invoice_id']}"))
    assert detail["exclusions"][-1]["reason"] == "FUNDING_FAILED"

    a = make_api("finance@member-a.test")
    new = own_statement(a, run["id"])
    assert new is not None and new["current"] and not new["approval"]["approval_count"]
    cases = ok(make_api("compliance@wise.test").get("/v1/admin/cases"))["items"]
    assert [(k["type"], k["subject_name"]) for k in cases] == [("FUNDING", "Member C")]
    drain()
    types = {
        n["type"] for n in ok(make_api("finance@member-c.test").get("/v1/notifications"))["items"]
    }
    assert "FUNDING_NEEDED" in types

    approve_all(make_api, run["id"])
    done = ok(settle(ops, run["id"]))
    assert done["status"] == "COMMITTED"
    assert all(x["balance_minor"] == 0 for x in done["settlement_detail"]["clearing"])
    assert {i["status"] for i in ok(c.get("/v1/invoices"))["items"]} == {"CONFIRMED"}
    assert ok(ops.get("/v1/windows/current"))["eligible_count"] == 3


def test_insufficient_funds_excludes_the_payer(make_api: Factory, fresh_db: Engine) -> None:
    ops, run = approved_run(make_api)
    ids = member_ids(fresh_db)
    with Session(fresh_db) as s, s.begin():
        ledger.post(
            s,
            kind=JournalKind.OPENING,
            idempotency_key="test:drain-a",
            lines=[
                PostingLine(
                    AccountRef(LedgerAccountType.MEMBER_BALANCE, ids["a"], "EUR"), -14_900_000
                ),
                PostingLine(AccountRef(LedgerAccountType.SUSPENSE, None, "EUR"), 14_900_000),
            ],
        )
    recomputed = ok(settle(ops, run["id"]))
    assert recomputed["current_attempt"] == 2
    with Session(fresh_db) as s:
        event = s.scalars(
            select(AuditEvent).where(AuditEvent.action == "settlement.member_excluded")
        ).one()
        assert (event.subject_id, event.reason_code) == (ids["a"], "FUNDING_FAILED")
        assert event.details == {"detail": "INSUFFICIENT_FUNDS"}


def test_abort_after_prepare_releases_every_hold(make_api: Factory, fresh_db: Engine) -> None:
    from app.core.db import session_factory
    from app.core.enums import SettlementStep
    from app.modules.settlement import service
    from tests.api.flows import ops_principal

    ops, run = approved_run(make_api)
    a = make_api("finance@member-a.test")
    opening = balances(a)
    with session_factory()() as s:
        service._run_step(s, ops_principal(s), UUID(run["id"]), 1, SettlementStep.PREPARE, "TEST")
    prepared = admin_run(ops, run["id"])
    assert prepared["status"] == "PREPARED"
    assert all(h["status"] == "ACTIVE" for h in prepared["settlement_detail"]["holds"])
    available, held = balances(a)["EUR"]
    assert held > 0 and available + held == opening["EUR"][0]
    assert ok(a.get(f"/v1/runs/{run['id']}"))["settlement"]["status"] == "FUNDS_HELD"

    # MC-RSK-03: with the global switch on, commit is refused and the holds stay in place.
    ok(
        ops.put(
            "/v1/admin/kill-switches", json={"scope": "GLOBAL", "enabled": True, "reason": "PAUSE"}
        )
    )
    assert error_code(settle(ops, run["id"])) == "KILL_SWITCH_ON"
    refused = admin_run(ops, run["id"])
    assert refused["status"] == "PREPARED"
    commit_job = next(j for j in refused["settlement_detail"]["jobs"] if j["step"] == "COMMIT")
    assert (commit_job["status"], commit_job["last_error"]) == ("FAILED", "KILL_SWITCH_ON")

    compliance = make_api("compliance@wise.test")
    assert (
        compliance.post(f"/v1/admin/runs/{run['id']}/abort", json={"reason_code": " "}).status_code
        == 422
    )
    aborted = ok(
        compliance.post(f"/v1/admin/runs/{run['id']}/abort", json={"reason_code": "OPS_ABORT"})
    )
    assert aborted["status"] == "ABORTED" and aborted["status_reason"] == "OPS_ABORT"
    assert {h["status"] for h in aborted["settlement_detail"]["holds"]} == {"RELEASED"}
    assert {t["status"] for t in aborted["settlement_detail"]["transfers"]} == {"CANCELLED"}
    assert balances(a) == opening
    assert {i["status"] for i in ok(a.get("/v1/invoices"))["items"]} == {"CONFIRMED"}
    check = ok(ops.get("/v1/admin/ledger/check"))
    assert check["ok"] and check["active_holds"] == 0
    again = compliance.post(f"/v1/admin/runs/{run['id']}/abort", json={"reason_code": "AGAIN"})
    assert ok(again)["status"] == "ABORTED"
    assert error_code(settle(ops, run["id"])) == "INVALID_STATE"


def test_commit_error_aborts_and_releases_every_hold(
    make_api: Factory, fresh_db: Engine, monkeypatch: Any
) -> None:
    from app.modules.settlement import service

    ops, run = approved_run(make_api)
    a = make_api("finance@member-a.test")
    opening = balances(a)

    def broken(*_: Any) -> Any:
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(service, "build_commit_postings", broken)
    aborted = ok(settle(ops, run["id"]))
    assert (aborted["status"], aborted["status_reason"]) == ("ABORTED", "COMMIT_ERROR")
    assert {h["status"] for h in aborted["settlement_detail"]["holds"]} == {"RELEASED"}
    commit_job = next(j for j in aborted["settlement_detail"]["jobs"] if j["step"] == "COMMIT")
    assert (commit_job["status"], commit_job["last_error"]) == ("FAILED", "RuntimeError")
    assert commit_entries(fresh_db, run["id"]) == 0
    assert balances(a) == opening
    assert ok(ops.get("/v1/admin/ledger/check"))["ok"]


def test_changed_frozen_input_aborts_in_prepare(make_api: Factory, fresh_db: Engine) -> None:
    ops, run = approved_run(make_api)
    with Session(fresh_db) as s, s.begin():
        s.execute(
            text(
                "UPDATE run_invoices SET outstanding_minor = outstanding_minor - 1 "
                "WHERE invoice_id = (SELECT invoice_id FROM run_invoices WHERE run_id = :r LIMIT 1)"
            ),
            {"r": run["id"]},
        )
    aborted = ok(settle(ops, run["id"]))
    assert (aborted["status"], aborted["status_reason"]) == ("ABORTED", "INPUT_CHANGED")
    assert aborted["settlement_detail"]["holds"] == []


def test_sanctions_hit_at_prepare_excludes_the_member(make_api: Factory, fresh_db: Engine) -> None:
    ops, run = approved_run(make_api)
    with Session(fresh_db) as s, s.begin():
        s.add(
            SanctionsEntry(
                name="Eastwind Electronics Ltd", country="GB", tax_id="GB000000005", source="TEST"
            )
        )
    recomputed = ok(settle(ops, run["id"]))
    assert recomputed["current_attempt"] == 2
    assert recomputed["computations"][-1]["trigger"] == "SANCTIONS_HIT"
    cases = ok(make_api("compliance@wise.test").get("/v1/admin/cases"))["items"]
    assert [(k["type"], k["subject_name"]) for k in cases] == [("SANCTIONS", "Member E")]
    e = make_api("finance@member-e.test")
    assert own_statement(e, run["id"]) is None
    # The counterparty sees a neutral reason, never the sanctions hit.
    d = make_api("finance@member-d.test")
    invoice = next(
        i for i in ok(d.get("/v1/invoices"))["items"] if i["invoice_number"] == "WX-2026-006"
    )
    assert ok(d.get(f"/v1/invoices/{invoice['id']}"))["exclusions"][-1]["reason"] == (
        "COUNTERPARTY_UNAVAILABLE"
    )


def usd_for_f(engine: Engine) -> None:
    with Session(engine) as s, s.begin():
        s.execute(
            update(Member)
            .where(Member.display_name == "Member F")
            .values(settlement_currency="USD")
        )


def test_multi_currency_commit_clears_every_currency(make_api: Factory, fresh_db: Engine) -> None:
    usd_for_f(fresh_db)
    ops = ready(make_api)
    run = close(ops)
    approve_all(make_api, run["id"])
    f = make_api("finance@member-f.test")
    s = own_statement(f, run["id"])
    assert s is not None and s["fx_legs"]
    usd_before = balances(f)["USD"][0]
    with Session(fresh_db) as session:
        assert session.scalar(select(func.count()).select_from(FxLock)) == 1
    done = ok(settle(ops, run["id"]))
    assert done["status"] == "COMMITTED"
    clearing = {c["currency"]: c["balance_minor"] for c in done["settlement_detail"]["clearing"]}
    assert clearing == {"EUR": 0, "USD": 0}
    assert s["instruction"]["type"] == "CREDIT"
    assert balances(f)["USD"][0] == usd_before + s["instruction"]["amount"]["amount_minor"]
    assert ok(ops.get("/v1/admin/ledger/check"))["ok"]


def test_expired_fx_lock_aborts_the_run(make_api: Factory, fresh_db: Engine) -> None:
    usd_for_f(fresh_db)
    ops = ready(make_api)
    run = close(ops)
    approve_all(make_api, run["id"])
    with Session(fresh_db) as s, s.begin():
        s.execute(update(FxLock).values(expires_at=utcnow() - timedelta(minutes=1)))
    aborted = ok(settle(ops, run["id"]))
    assert (aborted["status"], aborted["status_reason"]) == ("ABORTED", "FX_LOCK_EXPIRED")
    f = make_api("finance@member-f.test")
    assert {i["status"] for i in ok(f.get("/v1/invoices"))["items"]} == {"CONFIRMED"}


def test_expire_approvals_removes_non_responders(make_api: Factory) -> None:
    ops = ready(make_api)
    run = close(ops)
    approve_all(make_api, run["id"], codes="abcde")
    expired = ok(ops.post("/v1/demo/expire-approvals", json={"run_id": run["id"]}))
    assert expired["current_attempt"] == 2
    assert expired["computations"][-1]["trigger"] == "APPROVAL_EXPIRED"
    assert own_statement(make_api("finance@member-f.test"), run["id"]) is None
    approve_all(make_api, run["id"])
    again = ops.post("/v1/demo/expire-approvals", json={"run_id": run["id"]})
    assert error_code(again) == "INVALID_STATE"


def test_third_exclusion_through_funding_falls_back_to_gross(
    make_api: Factory, fresh_db: Engine
) -> None:
    ops, run = approved_run(make_api)
    ids = member_ids(fresh_db)
    # Payers only: a net receiver's fee comes out of its receipt, so it needs no funding.
    for attempt, code in enumerate("abe", start=1):
        ok(ops.post("/v1/demo/funding-failure", json={"member_id": str(ids[code])}))
        result = ok(settle(ops, run["id"]))
        if attempt < 3:
            assert (result["status"], result["current_attempt"]) == (
                "AWAITING_APPROVAL",
                attempt + 1,
            )
            approve_all(make_api, run["id"])
        else:
            assert result["status"] == "FALLBACK_GROSS"
    f = make_api("finance@member-f.test")
    assert {i["status"] for i in ok(f.get("/v1/invoices"))["items"]} == {"CONFIRMED"}
    assert ok(f.get(f"/v1/runs/{run['id']}"))["settlement"]["status"] == "CANCELLED"
    assert ok(ops.get("/v1/admin/ledger/check"))["active_holds"] == 0


def test_settlement_roles_and_states(make_api: Factory) -> None:
    ops = ready(make_api)
    run = close(ops)
    assert error_code(settle(ops, run["id"])) == "INVALID_STATE"
    assert settle(make_api("compliance@wise.test"), run["id"]).status_code == 403
    assert settle(make_api("admin@member-a.test"), run["id"]).status_code == 403
    assert (
        make_api("admin@member-a.test")
        .post(f"/v1/admin/runs/{run['id']}/abort", json={"reason_code": "NO"})
        .status_code
        == 403
    )
    assert settle(ops, str(uuid4())).status_code == 404
    blank = ops.post(f"/v1/admin/runs/{run['id']}/settle", json={"reason_code": ""})
    assert blank.status_code == 422
    assert make_api("finance@member-a.test").get("/v1/admin/ledger/check").status_code == 403


def test_run_can_be_traced_from_its_audit_events(make_api: Factory) -> None:
    ops, run = approved_run(make_api)
    ok(settle(ops, run["id"]))
    actions: list[str] = []
    cursor = None
    while True:
        page = ok(
            ops.get(
                f"/v1/admin/audit-events?run_id={run['id']}&limit=40"
                + (f"&cursor={cursor}" if cursor else "")
            )
        )
        actions += [e["action"] for e in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    actions.reverse()  # oldest first
    lifecycle = [a for a in actions if a.startswith("run.")]
    assert lifecycle == [
        "run.frozen",
        "run.screened",
        "run.computed",
        "run.awaiting_approval",
        "run.approved",
        "run.prepared",
        "run.committed",
    ]
    assert actions.count("settlement.hold_placed") == len(
        admin_run(ops, run["id"])["settlement_detail"]["holds"]
    )
    assert actions.count("invoice.settled_by_netting") == 2
    assert actions.count("invoice.settled_by_transfer") == 6
    settled = ok(ops.get(f"/v1/admin/audit-events?run_id={run['id']}&action=run.committed"))
    assert [e["reason_code"] for e in settled["items"]] == ["SETTLE"]
    assert ok(ops.get("/v1/admin/audit-events?action=settlement."))["items"]


def test_hold_rows_match_ledger_and_survive_the_append_only_rules(
    make_api: Factory, fresh_db: Engine
) -> None:
    ops, run = approved_run(make_api)
    ok(settle(ops, run["id"]))
    with Session(fresh_db) as s:
        holds = list(s.scalars(select(Hold)))
        assert holds and all(h.release_entry_id is not None for h in holds)
        report = ledger.check_chain(s)
        assert report.ok and report.entries > 0
