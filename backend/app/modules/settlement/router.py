from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.enums import Role
from app.core.idempotency import Idempotency, idempotency
from app.core.security import Principal, require_roles
from app.modules.runs.schemas import RunView
from app.modules.settlement import reads, service
from app.modules.settlement.schemas import LedgerCheck, ReasonRequest

router = APIRouter(prefix="/v1/admin", tags=["settlement"])


@router.post("/runs/{run_id}/settle", response_model=RunView)
def settle(
    run_id: UUID,
    body: ReasonRequest,
    actor: Principal = Depends(require_roles(Role.WISE_OPS)),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> RunView:
    """Prepare and commit; repeating it resumes an interrupted settlement or does nothing."""
    return cast(
        RunView,
        idem.run_steps(session, lambda s: service.settle(s, actor, run_id, body.reason_code)),
    )


@router.post("/runs/{run_id}/abort", response_model=RunView)
def abort(
    run_id: UUID,
    body: ReasonRequest,
    actor: Principal = Depends(require_roles(Role.WISE_OPS, Role.WISE_COMPLIANCE)),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> RunView:
    """Release every hold and return the run's invoices for the next window."""
    return cast(
        RunView, idem.run(session, lambda s: service.abort(s, actor, run_id, body.reason_code))
    )


@router.get("/ledger/check", response_model=LedgerCheck)
def ledger_check(
    actor: Principal = Depends(require_roles(Role.WISE_OPS, Role.WISE_COMPLIANCE)),
    session: Session = Depends(get_session),
) -> LedgerCheck:
    """Walk the journal hash chain and check every run's clearing and hold accounts."""
    return reads.ledger_check(session)
