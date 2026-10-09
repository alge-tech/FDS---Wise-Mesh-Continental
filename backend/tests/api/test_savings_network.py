"""Savings (MC-FEE), the break-even estimate, network views (MC-UX-02) and notifications."""

import json
from uuid import uuid4

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.events.worker import drain
from app.modules.audit.models import AuditEvent
from tests.api.flows import (
    Factory,
    approve_all,
    close,
    error_code,
    member_ids,
    ok,
    own_statement,
    ready,
    settle,
)


def test_savings_after_settlement_match_the_statement(make_api: Factory) -> None:
    ops = ready(make_api)
    run = close(ops)
    a = make_api("finance@member-a.test")
    pending = ok(a.get("/v1/savings"))
    assert [i["settled"] for i in pending["items"]] == [False]
    assert pending["totals"] == []
    approve_all(make_api, run["id"])
    ok(settle(ops, run["id"]))

    s = own_statement(a, run["id"])
    assert s is not None
    pricing = s["content"]["pricing"]
    body = ok(a.get("/v1/savings"))
    [item] = body["items"]
    assert item["settled"] and item["settled_at"]
    assert item["gross_payable"] == {"amount_minor": 10_000_000, "currency": "EUR"}
    assert item["net_paid"]["amount_minor"] == s["content"]["debit_minor"]
    assert item["baseline"]["amount_minor"] == pricing["baseline_minor"]
    assert item["fee"]["amount_minor"] == pricing["fee_minor"]
    assert item["savings"]["amount_minor"] == pricing["net_benefit_minor"] > 0
    [total] = body["totals"]
    assert total["runs"] == 1 and total["savings"] == item["savings"]


def test_estimates_reuse_the_real_allocation_and_change_nothing(
    make_api: Factory, fresh_db: Engine
) -> None:
    ops = ready(make_api)
    run = close(ops)
    a = make_api("finance@member-a.test")
    s = own_statement(a, run["id"])
    assert s is not None

    def audit_rows() -> int:
        with Session(fresh_db) as session:
            return int(session.scalar(select(func.count()).select_from(AuditEvent)) or 0)

    before = audit_rows()
    same = ok(
        a.post(
            "/v1/estimates",
            json={"run_id": run["id"], "standard_rate_bps": 52, "fee_share_bps": 2500},
        )
    )
    p = s["content"]["pricing"]
    assert (same["baseline"]["amount_minor"], same["fee"]["amount_minor"]) == (
        p["baseline_minor"],
        p["fee_minor"],
    )
    assert same["savings"]["amount_minor"] == p["net_benefit_minor"]
    assert same["source"] == "RUN" and same["break_even_fee_share_bps"] == 10_000

    typed = ok(
        a.post(
            "/v1/estimates",
            json={
                "gross_payable_minor": 10_000_000,
                "net_payable_minor": 4_000_000,
                "standard_rate_bps": 52,
                "fee_share_bps": 2500,
            },
        )
    )
    assert {k: typed[k]["amount_minor"] for k in ("baseline", "actual", "fee", "savings")} == {
        "baseline": 52_000,
        "actual": 28_600,
        "fee": 7_800,
        "savings": 23_400,
    }
    full_share = ok(
        a.post(
            "/v1/estimates",
            json={"run_id": run["id"], "standard_rate_bps": 52, "fee_share_bps": 10_000},
        )
    )
    assert full_share["savings"]["amount_minor"] == 0
    assert audit_rows() == before

    both = a.post(
        "/v1/estimates",
        json={
            "run_id": run["id"],
            "gross_payable_minor": 1,
            "net_payable_minor": 0,
            "standard_rate_bps": 52,
            "fee_share_bps": 2500,
        },
    )
    assert both.status_code == 422
    inverted = {"gross_payable_minor": 1, "net_payable_minor": 2}
    assert (
        a.post(
            "/v1/estimates", json={**inverted, "standard_rate_bps": 52, "fee_share_bps": 2500}
        ).status_code
        == 422
    )
    unknown = {"run_id": str(uuid4()), "standard_rate_bps": 52, "fee_share_bps": 2500}
    assert a.post("/v1/estimates", json=unknown).status_code == 404
    assert make_api("ops@wise.test").post("/v1/estimates", json=unknown).status_code == 403


def test_admin_network_before_and_after_netting(make_api: Factory) -> None:
    ops = ready(make_api)
    window = ok(ops.get("/v1/admin/network"))
    assert window["source"] == "WINDOW" and len(window["invoice_edges"]) == 8
    assert window["transfer_edges"] == []
    run = close(ops)
    graph = ok(ops.get("/v1/admin/network"))
    assert (graph["source"], graph["run_id"]) == ("RUN", run["id"])
    assert len(graph["nodes"]) == 6 and len(graph["invoice_edges"]) == 8
    assert graph["gross_minor"] == {"EUR": 45_000_000}
    assert graph["net_minor"] == {"EUR": 8_000_000}
    receivers = {e["target"] for e in graph["transfer_edges"]}
    names = {n["id"]: n["label"] for n in graph["nodes"]}
    assert [names[r] for r in receivers] == ["Member F"]
    assert len(graph["transfer_edges"]) == 3
    assert ok(ops.get(f"/v1/admin/network?run_id={run['id']}")) == graph
    assert ops.get(f"/v1/admin/network?run_id={uuid4()}").status_code == 404
    assert make_api("compliance@wise.test").get("/v1/admin/network").status_code == 403
    assert make_api("finance@member-a.test").get("/v1/admin/network").status_code == 403


def test_member_network_shows_only_own_counterparties(make_api: Factory, fresh_db: Engine) -> None:
    ops = ready(make_api)
    run = close(ops)
    a = make_api("finance@member-a.test")
    graph = ok(a.get("/v1/network/me"))
    labels = sorted(n["label"] for n in graph["nodes"])
    assert labels == [
        "Baltic Freight SIA",
        "Castell Textiles SL",
        "Member A",
        "Mesh settlement",
    ]
    [transfer] = graph["transfer_edges"]
    s = own_statement(a, run["id"])
    assert s is not None
    assert (transfer["source"], transfer["target"]) == ("self", "mesh")
    assert transfer["amount_minor"] == s["content"]["debit_minor"]
    ids = member_ids(fresh_db)
    raw = json.dumps(graph)
    assert not any(str(ids[c]) in raw for c in "def")  # no member beyond A's counterparties


def test_notifications_list_and_read(make_api: Factory) -> None:
    ops = ready(make_api)
    close(ops)
    drain()
    a = make_api("finance@member-a.test")
    body = ok(a.get("/v1/notifications"))
    assert body["unread_count"] >= 1
    statement_ready = next(n for n in body["items"] if n["type"] == "STATEMENT_READY")
    read = ok(a.post(f"/v1/notifications/{statement_ready['id']}/read"))
    assert read["unread_count"] == body["unread_count"] - 1
    other = make_api("finance@member-b.test")
    assert error_code(other.post(f"/v1/notifications/{statement_ready['id']}/read")) == "NOT_FOUND"
