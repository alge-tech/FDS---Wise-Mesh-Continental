from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.enums import Role
from app.core.errors import NotFound
from app.core.idempotency import Idempotency, idempotency
from app.core.schemas import Page
from app.core.security import (
    MemberContext,
    Principal,
    current_principal,
    member_context,
    require_roles,
)
from app.modules.runs import reads, repository, service
from app.modules.runs.schemas import (
    AdminOverview,
    ApprovalRequest,
    CloseRequest,
    KillRequest,
    RunView,
    StatementView,
    WindowView,
    WithdrawalRequest,
)
from app.modules.statements import service as statements

router = APIRouter(prefix="/v1", tags=["runs"])


@router.get("/windows/current", response_model=WindowView)
def current(
    actor: Principal = Depends(current_principal), session: Session = Depends(get_session)
) -> WindowView:
    return reads.current_window(session, actor)


@router.post("/admin/windows/current/close", response_model=RunView)
def close(
    body: CloseRequest,
    actor: Principal = Depends(require_roles(Role.WISE_OPS)),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> RunView:
    return cast(
        RunView,
        idem.run(
            session, lambda s: reads.run_view(s, service.close(s, actor, body.reason_code), None)
        ),
    )


@router.get("/runs", response_model=Page[RunView])
def list_runs(
    ctx: MemberContext = Depends(member_context()), session: Session = Depends(get_session)
) -> Page[RunView]:
    return Page(
        items=[
            reads.run_view(session, r, ctx.member_id)
            for r in repository.list_for_member(session, ctx.member_id)
        ]
    )


@router.get("/runs/{run_id}", response_model=RunView)
def run(
    run_id: UUID,
    ctx: MemberContext = Depends(member_context()),
    session: Session = Depends(get_session),
) -> RunView:
    row = repository.get_for_member(session, ctx.member_id, run_id)
    if row is None:
        raise NotFound()
    return reads.run_view(session, row, ctx.member_id)


@router.get("/statements/{statement_id}", response_model=StatementView)
def statement(
    statement_id: UUID,
    ctx: MemberContext = Depends(member_context()),
    session: Session = Depends(get_session),
) -> StatementView:
    return reads.statement_view(session, ctx.principal, statement_id)


@router.post("/statements/{statement_id}/approvals", response_model=RunView)
def approve(
    statement_id: UUID,
    body: ApprovalRequest,
    ctx: MemberContext = Depends(member_context()),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> RunView:
    return cast(
        RunView,
        idem.run(session, lambda s: statements.approve(s, ctx.principal, statement_id, body)),
    )


@router.get("/admin/overview", response_model=AdminOverview)
def overview(
    actor: Principal = Depends(require_roles(Role.WISE_OPS, Role.WISE_COMPLIANCE)),
    session: Session = Depends(get_session),
) -> AdminOverview:
    return reads.overview(session)


@router.get("/admin/runs/{run_id}", response_model=RunView)
def admin_run(
    run_id: UUID,
    actor: Principal = Depends(require_roles(Role.WISE_OPS, Role.WISE_COMPLIANCE)),
    session: Session = Depends(get_session),
) -> RunView:
    return reads.run_view(session, service.get_admin(session, run_id), None)


@router.put("/admin/kill-switches", response_model=AdminOverview)
def switches(
    body: KillRequest,
    actor: Principal = Depends(require_roles(Role.WISE_OPS, Role.WISE_COMPLIANCE)),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> AdminOverview:
    from app.modules.admin.service import set_switch

    return cast(AdminOverview, idem.run(session, lambda s: set_switch(s, actor, body)))


@router.post("/runs/{run_id}/withdrawals", response_model=RunView)
def withdraw(
    run_id: UUID,
    body: WithdrawalRequest,
    ctx: MemberContext = Depends(member_context(Role.MEMBER_ADMIN, Role.FINANCE_USER)),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> RunView:
    """MC-APR-03: withdraw own invoices from the run; the run recomputes."""
    ids = {UUID(i) for i in body.invoice_ids}
    return cast(
        RunView,
        idem.run(
            session,
            lambda s: reads.run_view(
                s,
                service.withdraw(s, ctx.principal, run_id, ids, body.reason_code),
                ctx.member_id,
            ),
        ),
    )
