from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.enums import InvoiceSource, Role
from app.core.idempotency import Idempotency, idempotency
from app.core.schemas import Page
from app.core.security import MemberContext, member_context
from app.modules.confirmations import service as confirmations
from app.modules.invoices import repository, service
from app.modules.invoices.parsing import template_csv
from app.modules.invoices.schemas import (
    ConfirmationRequest,
    InvoiceCreate,
    InvoiceDetail,
    InvoiceView,
    UploadResult,
)

router = APIRouter(prefix="/v1", tags=["invoices"])
write = member_context(Role.FINANCE_USER, Role.MEMBER_ADMIN)


@router.get("/invoices/template.csv", response_class=Response)
def template(ctx: MemberContext = Depends(member_context())) -> Response:
    return Response(
        template_csv("YOUR_TAX_ID", "COUNTERPARTY_TAX_ID"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="mesh-invoices.csv"'},
    )


async def csv_body(request: Request) -> bytes:
    return await request.body()


@router.post(
    "/invoices/uploads",
    response_model=UploadResult,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
def upload(
    content: bytes = Depends(csv_body),
    ctx: MemberContext = Depends(write),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> UploadResult:
    return cast(
        UploadResult,
        idem.run(session, lambda s: service.upload(s, content, ctx.member_id, ctx.principal)),
    )


@router.post("/invoices", response_model=InvoiceView, status_code=201)
def create(
    body: InvoiceCreate,
    ctx: MemberContext = Depends(write),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> InvoiceView:
    return cast(
        InvoiceView,
        idem.run(
            session,
            lambda s: service.view(
                s,
                service.create(
                    s, service.parse(s, body), ctx.member_id, ctx.principal, InvoiceSource.MANUAL
                ),
                ctx.member_id,
            ),
            status_code=201,
        ),
    )


@router.get("/invoices", response_model=Page[InvoiceView])
def list_invoices(
    direction: Literal["RECEIVABLE", "PAYABLE"] | None = None,
    status: list[str] | None = Query(default=None),
    counterparty: UUID | None = None,
    cursor: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    ctx: MemberContext = Depends(member_context()),
    session: Session = Depends(get_session),
) -> Page[InvoiceView]:
    rows = repository.list_for_member(
        session,
        ctx.member_id,
        direction=direction,
        statuses=status,
        counterparty=counterparty,
        limit=limit + 1,
        cursor=cursor,
    )
    return Page(
        items=[service.view(session, i, ctx.member_id) for i in rows[:limit]],
        next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetail)
def detail(
    invoice_id: UUID,
    ctx: MemberContext = Depends(member_context()),
    session: Session = Depends(get_session),
) -> InvoiceDetail:
    return service.detail(session, ctx.member_id, invoice_id)


@router.get("/confirmations", response_model=Page[InvoiceView])
def inbox(
    ctx: MemberContext = Depends(write), session: Session = Depends(get_session)
) -> Page[InvoiceView]:
    return Page(
        items=[
            service.view(session, i, ctx.member_id)
            for i in confirmations.inbox(session, ctx.member_id)
        ]
    )


@router.post("/invoices/{invoice_id}/confirmations", response_model=InvoiceView)
def decide(
    invoice_id: UUID,
    body: ConfirmationRequest,
    ctx: MemberContext = Depends(write),
    idem: Idempotency = Depends(idempotency),
    session: Session = Depends(get_session),
) -> InvoiceView:
    return cast(
        InvoiceView,
        idem.run(
            session,
            lambda s: service.view(
                s,
                confirmations.decide(s, ctx.member_id, invoice_id, body, ctx.principal),
                ctx.member_id,
            ),
        ),
    )
