from typing import cast

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.enums import Role
from app.core.idempotency import Idempotency, idempotency
from app.core.security import MemberContext, member_context
from app.modules.members import service
from app.modules.members.schemas import MemberDetail, SettingsUpdate

router = APIRouter(prefix="/v1", tags=["members"])


@router.get("/members/me", response_model=MemberDetail)
def get_my_member(
    ctx: MemberContext = Depends(member_context()), session: Session = Depends(get_session)
) -> MemberDetail:
    return service.member_detail(session, ctx)


@router.patch("/members/me/settings", response_model=MemberDetail)
def update_settings(
    body: SettingsUpdate,
    ctx: MemberContext = Depends(member_context(Role.MEMBER_ADMIN)),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> MemberDetail:
    return cast(MemberDetail, idem.run(session, lambda s: service.update_settings(s, ctx, body)))
