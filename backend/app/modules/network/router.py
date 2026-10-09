from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.enums import Role
from app.core.security import MemberContext, Principal, member_context, require_roles
from app.modules.network import service
from app.modules.network.schemas import NetworkView

router = APIRouter(prefix="/v1", tags=["network"])


@router.get("/admin/network", response_model=NetworkView)
def admin_network(
    run_id: UUID | None = None,
    actor: Principal = Depends(require_roles(Role.WISE_OPS)),
    session: Session = Depends(get_session),
) -> NetworkView:
    """The whole graph: gross invoice edges before netting, settlement transfers after."""
    return service.admin_network(session, run_id)


@router.get("/network/me", response_model=NetworkView)
def my_network(
    ctx: MemberContext = Depends(member_context()), session: Session = Depends(get_session)
) -> NetworkView:
    """Own counterparties and flows only; the settlement counterparty is Mesh settlement."""
    return service.member_network(session, ctx.member_id)
