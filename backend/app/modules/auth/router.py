from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import Principal, clear_session, current_principal, issue_session
from app.modules.members import service
from app.modules.members.schemas import LoginRequest, Me

router = APIRouter(prefix="/v1", tags=["auth"])


@router.post("/auth/login", response_model=Me)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> Me:
    ip = request.client.host if request.client else "unknown"
    user = service.authenticate(session, body.email, body.password, ip)
    issue_session(response, user.id)
    from app.core.enums import Role

    return service.me(session, Principal(user.id, Role(user.role), user.member_id, user.email))


@router.post("/auth/logout", status_code=204)
def logout(response: Response) -> Response:
    clear_session(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=Me)
def get_me(
    principal: Principal = Depends(current_principal), session: Session = Depends(get_session)
) -> Me:
    return service.me(session, principal)
