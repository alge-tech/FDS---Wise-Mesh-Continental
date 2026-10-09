from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import MemberContext, member_context
from app.modules.members import service
from app.modules.members.schemas import MemberDetail

router = APIRouter(prefix="/v1", tags=["members"])


@router.get("/members/me", response_model=MemberDetail)
def get_my_member(
    ctx: MemberContext = Depends(member_context()), session: Session = Depends(get_session)
) -> MemberDetail:
    return service.member_detail(session, ctx)
