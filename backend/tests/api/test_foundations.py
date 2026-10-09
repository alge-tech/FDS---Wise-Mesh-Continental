"""M0 gate and cross-cutting API conventions: auth, CSRF, errors, idempotency, ledger."""

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.ledger.service import check_chain
from tests.api.conftest import Api

ApiFactory = Callable[..., Api]


def test_seeded_user_logs_in_and_sees_own_balance(make_api: ApiFactory) -> None:
    api = make_api("finance@member-a.test")
    me = api.get("/v1/me").json()
    assert me["role"] == "FINANCE_USER"
    assert me["member"]["name"] == "Member A"
    detail = api.get("/v1/members/me").json()
    eur = next(b for b in detail["balances"] if b["currency"] == "EUR")
    assert eur["available"] == {"amount_minor": 15_000_000, "currency": "EUR"}
    assert eur["held"]["amount_minor"] == 0


@pytest.mark.parametrize("code", list("ABCDEF"))
def test_every_member_user_sees_only_its_own_member(make_api: ApiFactory, code: str) -> None:
    for kind in ("admin", "finance", "approver"):
        me = make_api(f"{kind}@member-{code.lower()}.test").get("/v1/me").json()
        assert me["member"]["name"] == f"Member {code}"


def test_wrong_password_is_refused_with_envelope(make_api: ApiFactory) -> None:
    r = make_api().client.post(
        "/v1/auth/login",
        json={"email": "finance@member-a.test", "password": "nope"},
        headers={"X-Requested-With": "mesh-web"},
    )
    assert r.status_code == 401
    body = r.json()["error"]
    assert body["code"] == "INVALID_CREDENTIALS"
    assert body["correlation_id"] == r.headers["x-correlation-id"]


def test_login_is_rate_limited_per_email(make_api: ApiFactory) -> None:
    client = make_api().client
    codes = [
        client.post(
            "/v1/auth/login",
            json={"email": "admin@member-b.test", "password": "wrong"},
            headers={"X-Requested-With": "mesh-web"},
        ).status_code
        for _ in range(12)
    ]
    assert codes[-1] == 429


def test_state_changing_request_needs_csrf_header(make_api: ApiFactory) -> None:
    api = make_api("ops@wise.test")
    r = api.client.post("/v1/demo/reset", headers={"Idempotency-Key": "k1"})
    assert r.status_code == 403
    r = api.client.post(
        "/v1/demo/reset",
        headers={
            "X-Requested-With": "mesh-web",
            "Idempotency-Key": "k1",
            "Origin": "https://evil.example",
        },
    )
    assert r.status_code == 403


def test_unauthenticated_request_gets_401(make_api: ApiFactory) -> None:
    r = make_api().get("/v1/members/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_staff_cannot_use_member_endpoints(make_api: ApiFactory) -> None:
    r = make_api("ops@wise.test").get("/v1/members/me")
    assert r.status_code == 403


def test_member_cannot_use_demo_controls(make_api: ApiFactory) -> None:
    r = make_api("admin@member-a.test").post("/v1/demo/reset")
    assert r.status_code == 403


def test_idempotency_key_required_and_replayed(make_api: ApiFactory) -> None:
    """A throwaway route that writes one audit row per real execution."""
    from fastapi import APIRouter, Depends
    from sqlalchemy import func, select

    from app.core.db import get_session
    from app.core.idempotency import Idempotency, idempotency
    from app.modules.audit import service as audit
    from app.modules.audit.models import AuditEvent

    api = make_api("ops@wise.test")
    router = APIRouter()

    @router.post("/v1/_test/touch")
    def touch(
        body: dict[str, int],
        idem: Idempotency = Depends(idempotency),
        session: Session = Depends(get_session),
    ) -> dict[str, int]:
        def work(s: Session) -> dict[str, int]:
            audit.record(
                s,
                actor=idem.principal,
                action="test.touch",
                subject_type="TEST",
                subject_id=idem.principal.user_id,
            )
            return {"n": body["n"]}

        return idem.run(session, work, status_code=201)  # type: ignore[no-any-return]

    api.client.app.include_router(router)  # type: ignore[attr-defined]

    def touches() -> int:
        with Session(api_engine()) as s:
            return int(
                s.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "test.touch")
                )
                or 0
            )

    missing = api.client.post(
        "/v1/_test/touch", json={"n": 1}, headers={"X-Requested-With": "mesh-web"}
    )
    assert missing.status_code == 422
    first = api.post("/v1/_test/touch", key="k-1", json={"n": 1})
    assert first.status_code == 201, first.text
    replay = api.post("/v1/_test/touch", key="k-1", json={"n": 1})
    assert (replay.status_code, replay.json()) == (201, {"n": 1})
    assert touches() == 1
    mismatch = api.post("/v1/_test/touch", key="k-1", json={"n": 2})
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "IDEMPOTENCY_MISMATCH"
    assert api.post("/v1/_test/touch", key="k-2", json={"n": 2}).status_code == 201
    assert touches() == 2


def api_engine():  # type: ignore[no-untyped-def]
    from app.core.db import get_engine

    return get_engine()


def test_demo_reset_reseeds_and_keeps_sessions(make_api: ApiFactory) -> None:
    ops = make_api("ops@wise.test")
    member = make_api("finance@member-a.test")
    r = ops.post("/v1/demo/reset")
    assert r.status_code == 200, r.text
    # Seeded users keep their IDs, so sessions opened before the reset still work.
    assert ops.get("/v1/admin/overview").status_code == 200
    assert member.get("/v1/me").json()["member"]["name"] == "Member A"


def test_personas_list_staff_first(make_api: ApiFactory) -> None:
    body = make_api().get("/v1/demo/personas").json()
    assert body["items"][0]["role"] == "WISE_OPS"
    assert len(body["items"]) == 2 + 6 * 3


def test_currencies_and_rates(make_api: ApiFactory) -> None:
    api = make_api("finance@member-c.test")
    codes = {c["code"]: c["exponent"] for c in api.get("/v1/currencies").json()["items"]}
    assert codes == {"EUR": 2, "USD": 2, "HUF": 2, "GBP": 2, "CNY": 2}
    rates = api.get("/v1/rates").json()["items"]
    assert any(r["base"] == "EUR" and r["quote"] == "USD" and r["rate"] == "1.085" for r in rates)


def test_ledger_is_append_only_for_the_app_role(session: Session) -> None:
    with pytest.raises(DBAPIError):
        session.execute(text("UPDATE postings SET amount_minor = amount_minor"))
    session.rollback()
    with pytest.raises(DBAPIError):
        session.execute(text("DELETE FROM audit_events"))
    session.rollback()


def test_ledger_is_append_only_even_for_the_owner(owner_engine, fresh_db) -> None:  # type: ignore[no-untyped-def]
    with Session(owner_engine) as s:
        with pytest.raises(DBAPIError, match="append-only"):
            s.execute(text("UPDATE journal_entries SET kind = kind"))
        s.rollback()


def test_seed_balances_and_hash_chain(session: Session) -> None:
    report = check_chain(session)
    assert report.ok
    assert report.entries == sum(
        len(m.opening_balances_major)
        for m in __import__("app.modules.demo.scenarios", fromlist=["MEMBERS"]).MEMBERS
    )
    session.rollback()
    session.execute(text("SELECT 1"))


def test_healthz(make_api: ApiFactory) -> None:
    r = make_api().get("/healthz")
    assert r.json() == {"status": "ok", "database": "reachable"}
