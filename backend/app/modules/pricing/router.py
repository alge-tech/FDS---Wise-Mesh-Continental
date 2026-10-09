from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import MemberContext, member_context
from app.modules.pricing import service
from app.modules.pricing.schemas import Estimate, EstimateRequest, SavingsSummary

router = APIRouter(prefix="/v1", tags=["pricing"])


@router.get("/savings", response_model=SavingsSummary)
def savings(
    ctx: MemberContext = Depends(member_context()), session: Session = Depends(get_session)
) -> SavingsSummary:
    """Per-run and cumulative savings; totals count settled runs only."""
    return service.savings(session, ctx.member_id)


@router.post("/estimates", response_model=Estimate)
def estimate(
    body: EstimateRequest,
    ctx: MemberContext = Depends(member_context()),
    session: Session = Depends(get_session),
) -> Estimate:
    """Break-even calculation. Read-only, so no Idempotency-Key is needed."""
    return service.estimate(session, ctx.member_id, body)
