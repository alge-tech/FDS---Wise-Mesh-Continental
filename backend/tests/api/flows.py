"""Shared demo-path steps for the API and settlement tests."""

from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.core.security import Principal
from app.modules.members.models import Member, User
from tests.api.conftest import Api

Factory = Callable[..., Api]
CODES = "abcdef"


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def error_code(response: Any) -> str:
    return str(response.json()["error"]["code"])


def ready(make_api: Factory, scenario: str = "worked_example") -> Api:
    """Ops loads a scenario and every counterparty confirms."""
    ops = make_api("ops@wise.test")
    ok(ops.post(f"/v1/demo/scenarios/{scenario}"))
    ok(ops.post("/v1/demo/simulate-confirmations", json={"confirm_pct": 100}))
    return ops


def close(ops: Api) -> dict[str, Any]:
    return ok(ops.post("/v1/admin/windows/current/close", json={"reason_code": "DEMO_CLOSE"}))  # type: ignore[no-any-return]


def own_statement(api: Api, run_id: str) -> dict[str, Any] | None:
    run = ok(api.get(f"/v1/runs/{run_id}"))
    if not run["statement_id"]:
        return None
    return ok(api.get(f"/v1/statements/{run['statement_id']}"))  # type: ignore[no-any-return]


def answer(api: Api, s: dict[str, Any], decision: str = "APPROVE") -> Any:
    return api.post(
        f"/v1/statements/{s['statement_id']}/approvals",
        json={"decision": decision, "content_hash": s["content_hash"]},
    )


def approve_all(make_api: Factory, run_id: str, codes: str = CODES) -> None:
    """Every listed member with a current statement approves it (admins pass maker-checker)."""
    for code in codes:
        for kind in ("admin", "approver"):
            api = make_api(f"{kind}@member-{code}.test")
            s = own_statement(api, run_id)
            if s and s["approval"]["can_approve"]:
                ok(answer(api, s))


def settle(ops: Api, run_id: str, key: str | None = None) -> Any:
    return ops.post(f"/v1/admin/runs/{run_id}/settle", key=key, json={"reason_code": "SETTLE"})


def admin_run(ops: Api, run_id: str) -> dict[str, Any]:
    return ok(ops.get(f"/v1/admin/runs/{run_id}"))  # type: ignore[no-any-return]


def balances(api: Api) -> dict[str, tuple[int, int]]:
    """currency -> (available, held), derived from postings by the API."""
    detail = ok(api.get("/v1/members/me"))
    return {
        b["currency"]: (b["available"]["amount_minor"], b["held"]["amount_minor"])
        for b in detail["balances"]
    }


def member_ids(engine: Engine) -> dict[str, Any]:
    with Session(engine) as s:
        return {
            m.display_name[-1].lower(): m.id
            for m in s.scalars(select(Member).where(Member.display_name.like("Member _")))
        }


def ops_principal(session: Session) -> Principal:
    user = session.scalars(select(User).where(User.email == "ops@wise.test")).one()
    return Principal(user.id, Role.WISE_OPS, None, user.email)
