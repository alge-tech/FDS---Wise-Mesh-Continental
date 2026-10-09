"""Settlement scenarios: crash safety, and dust carried forward into the next run."""

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.core.db import session_factory
from app.core.enums import JournalKind, LedgerAccountType
from app.modules.ledger.models import JournalEntry, LedgerAccount, Posting
from app.modules.settlement import service
from app.modules.settlement.models import Hold, SettlementJob
from tests.api.flows import (
    Factory,
    admin_run,
    approve_all,
    close,
    member_ids,
    ok,
    ops_principal,
    own_statement,
    ready,
    settle,
)


class Crash(BaseException):
    """Stands in for the process dying: no `except Exception` handler sees it."""


def commits(engine: Engine, run_id: str) -> int:
    with Session(engine) as s:
        return int(
            s.scalar(
                select(func.count())
                .select_from(JournalEntry)
                .where(JournalEntry.run_id == UUID(run_id), JournalEntry.kind == JournalKind.COMMIT)
            )
            or 0
        )


def commit_job(engine: Engine, run_id: str) -> SettlementJob:
    with Session(engine) as s:
        return s.scalars(
            select(SettlementJob).where(
                SettlementJob.run_id == UUID(run_id), SettlementJob.step == "COMMIT"
            )
        ).one()


@pytest.mark.parametrize("crash_point", ["between_steps", "inside_commit"])
def test_crash_still_ends_in_exactly_one_commit(
    make_api: Factory, fresh_db: Engine, monkeypatch: Any, crash_point: str
) -> None:
    ops = ready(make_api)
    run = close(ops)
    approve_all(make_api, run["id"])

    if crash_point == "between_steps":
        # Prepare committed its transaction; the process dies before commit starts its own.
        def crash(*_: Any) -> Any:
            raise Crash

        monkeypatch.setattr(service, "_commit", crash)
    else:
        # The commit entry is posted, then the process dies before the transaction commits.
        def crash_after_posting(*_: Any) -> Any:
            raise Crash

        monkeypatch.setattr(service, "_write_outcomes", crash_after_posting)

    with session_factory()() as s, pytest.raises(Crash):
        service.settle(s, ops_principal(s), UUID(run["id"]), "SETTLE")
    monkeypatch.undo()

    stuck = admin_run(ops, run["id"])
    assert stuck["status"] == "PREPARED"
    assert {h["status"] for h in stuck["settlement_detail"]["holds"]} == {"ACTIVE"}
    job = commit_job(fresh_db, run["id"])
    assert (job.status, job.attempts) == ("STARTED", 1)  # written before the step began
    assert commits(fresh_db, run["id"]) == 0

    resumed = ok(settle(ops, run["id"]))
    assert resumed["status"] == "COMMITTED"
    assert commits(fresh_db, run["id"]) == 1
    job = commit_job(fresh_db, run["id"])
    assert (job.status, job.attempts) == ("DONE", 2)
    assert ok(settle(ops, run["id"]))["status"] == "COMMITTED"
    assert commits(fresh_db, run["id"]) == 1
    assert ok(ops.get("/v1/admin/ledger/check"))["ok"]


def invoice(api: Any, number: str, issuer: str, payer: str, amount: str) -> None:
    body = {
        "invoice_number": number,
        "issuer_tax_id": issuer,
        "payer_tax_id": payer,
        "currency": "EUR",
        "amount": amount,
        "issue_date": "2026-10-01",
        "due_date": "2026-10-31",
    }
    ok(api.post("/v1/invoices", json=body), 201)


def suspense(engine: Engine, member_id: UUID) -> int:
    with Session(engine) as s:
        return int(
            s.scalar(
                select(func.coalesce(func.sum(Posting.amount_minor), 0))
                .join(LedgerAccount, LedgerAccount.id == Posting.account_id)
                .where(
                    LedgerAccount.type == LedgerAccountType.SUSPENSE,
                    LedgerAccount.member_id == member_id,
                )
            )
            or 0
        )


def test_dust_is_parked_in_suspense_and_paid_out_in_the_next_run(
    make_api: Factory, fresh_db: Engine
) -> None:
    """MC-FX-04: a residual below the dust threshold carries forward to the next window."""
    a_tax, b_tax = "DE811000001", "LV400000002"
    ids = member_ids(fresh_db)
    a, ops = make_api("finance@member-a.test"), make_api("ops@wise.test")
    invoice(a, "DUST-1", b_tax, a_tax, "10000.50")  # A owes B 10,000.50
    invoice(a, "DUST-2", a_tax, b_tax, "10000.00")  # B owes A 10,000.00
    ok(ops.post("/v1/demo/simulate-confirmations", json={}))
    first = close(ops)
    s = own_statement(a, first["id"])
    assert s is not None
    assert (s["net"]["amount_minor"], s["carried"]["amount_minor"]) == (0, -50)
    approve_all(make_api, first["id"], codes="ab")
    assert ok(settle(ops, first["id"]))["status"] == "COMMITTED"
    assert (suspense(fresh_db, ids["a"]), suspense(fresh_db, ids["b"])) == (-50, 50)

    invoice(a, "DUST-3", b_tax, a_tax, "100.00")  # A owes B 100.00
    ok(ops.post("/v1/demo/simulate-confirmations", json={}))
    second = close(ops)
    s = own_statement(a, second["id"])
    assert s is not None
    assert s["net"]["amount_minor"] == -10_050  # 100.00 plus the 0.50 carried in
    metrics = admin_run(ops, second["id"])["computations"][0]["metrics"]
    assert sorted(c["amount_minor"] for c in metrics["carry_in_used"]) == [-50, 50]
    approve_all(make_api, second["id"], codes="ab")
    done = ok(settle(ops, second["id"]))
    assert done["status"] == "COMMITTED"
    assert all(c["balance_minor"] == 0 for c in done["settlement_detail"]["clearing"])
    assert (suspense(fresh_db, ids["a"]), suspense(fresh_db, ids["b"])) == (0, 0)
    assert ok(ops.get("/v1/admin/ledger/check"))["ok"]


def test_only_one_active_run_claims_carried_dust(make_api: Factory, fresh_db: Engine) -> None:
    """With an earlier run still in flight, a new run leaves suspense balances alone."""
    from app.core.enums import RunStatus
    from app.modules.runs import service as runs
    from app.modules.runs.models import NettingRun

    ops = ready(make_api)
    first = close(ops)
    with Session(fresh_db) as s:
        run = s.get(NettingRun, UUID(first["id"]))
        assert run is not None and run.status == RunStatus.AWAITING_APPROVAL
        other = NettingRun(window_id=run.window_id, input_hash="x", status=RunStatus.FROZEN)
        assert runs.carry_in(s, other) == ()
    with Session(fresh_db) as s:
        assert not list(s.scalars(select(Hold)))
