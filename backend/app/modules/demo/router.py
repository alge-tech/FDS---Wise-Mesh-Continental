"""Demo controls (`DEMO_MODE` only). Every action is a Wise ops action and is audited."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.enums import STAFF_ROLES, Role
from app.core.errors import AppError
from app.core.idempotency import Idempotency, idempotency
from app.core.schemas import ApiModel
from app.core.security import Principal, require_roles
from app.modules.demo import invoices as demo_invoices
from app.modules.demo import service
from app.modules.demo import settlement as demo_settlement
from app.modules.members.models import Member, User
from app.modules.runs.schemas import RunView

router = APIRouter(prefix="/v1/demo", tags=["demo"])


class DemoModeOff(AppError):
    status_code = 404
    code = "DEMO_MODE_OFF"


def demo_mode() -> None:
    if not get_settings().demo_mode:
        raise DemoModeOff("Demo controls are switched off.")


class Persona(ApiModel):
    email: str
    display_name: str
    role: Role
    member_name: str | None


class PersonaList(ApiModel):
    password: str
    items: list[Persona]


class ResetResult(ApiModel):
    ok: bool


@router.get("/personas", response_model=PersonaList, dependencies=[Depends(demo_mode)])
def personas(session: Session = Depends(get_session)) -> PersonaList:
    rows = session.execute(
        select(User, Member.display_name)
        .outerjoin(Member, Member.id == User.member_id)
        .order_by(Member.display_name.nulls_first(), User.role, User.email)
    ).all()
    order = {Role.WISE_OPS: 0, Role.WISE_COMPLIANCE: 1}
    items = [
        Persona(email=u.email, display_name=u.display_name, role=Role(u.role), member_name=name)
        for u, name in rows
    ]
    items.sort(key=lambda p: (p.member_name is not None, order.get(p.role, 9), p.member_name or ""))
    return PersonaList(password=get_settings().demo_password, items=items)


@router.post("/reset", response_model=ResetResult, dependencies=[Depends(demo_mode)])
def reset(
    principal: Principal = Depends(require_roles(Role.WISE_OPS)),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> ResetResult:
    assert principal.role in STAFF_ROLES
    return idem.run_steps(session, lambda s: service.reset(s, principal))  # type: ignore[no-any-return]


@router.post("/scenarios/{name}", dependencies=[Depends(demo_mode)])
def scenario(
    name: str,
    principal: Principal = Depends(require_roles(Role.WISE_OPS)),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return idem.run(session, lambda s: demo_invoices.scenario(s, name, principal))  # type: ignore[no-any-return]


@router.post("/simulate-confirmations", dependencies=[Depends(demo_mode)])
def simulate(
    body: demo_invoices.Simulate,
    principal: Principal = Depends(require_roles(Role.WISE_OPS)),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> dict[str, int]:
    return idem.run(session, lambda s: demo_invoices.simulate(s, body, principal))  # type: ignore[no-any-return]


@router.post("/generate", dependencies=[Depends(demo_mode)])
def generate(
    body: demo_invoices.Generate,
    principal: Principal = Depends(require_roles(Role.WISE_OPS)),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> dict[str, int]:
    return idem.run(session, lambda s: demo_invoices.generate(s, body, principal))  # type: ignore[no-any-return]


@router.post(
    "/funding-failure",
    response_model=demo_settlement.FundingState,
    dependencies=[Depends(demo_mode)],
)
def funding_failure(
    body: demo_settlement.FundingFailure,
    principal: Principal = Depends(require_roles(Role.WISE_OPS)),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> demo_settlement.FundingState:
    """Mark a payer as unable to fund (or able again); the next prepare excludes it."""
    return idem.run(  # type: ignore[no-any-return]
        session, lambda s: demo_settlement.funding_failure(s, body, principal)
    )


@router.post("/expire-approvals", response_model=RunView, dependencies=[Depends(demo_mode)])
def expire_approvals(
    body: demo_settlement.ExpireApprovals,
    principal: Principal = Depends(require_roles(Role.WISE_OPS)),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> RunView:
    """Remove members who have not approved, then recompute (the approval deadline)."""
    return idem.run(  # type: ignore[no-any-return]
        session, lambda s: demo_settlement.expire_approvals(s, body, principal)
    )
