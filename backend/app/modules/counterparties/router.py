from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.schemas import Page
from app.core.security import MemberContext, member_context
from app.modules.counterparties.service import list_for_member
from app.modules.invoices.schemas import CounterpartyView

router = APIRouter(prefix="/v1/counterparties", tags=["counterparties"])


@router.get("", response_model=Page[CounterpartyView])
def counterparties(
    ctx: MemberContext = Depends(member_context()), session: Session = Depends(get_session)
) -> Page[CounterpartyView]:
    return Page(items=list_for_member(session, ctx.member_id))
