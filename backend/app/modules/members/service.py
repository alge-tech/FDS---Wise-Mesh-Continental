from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFound, Unauthenticated
from app.core.ratelimit import check_login_allowed
from app.core.schemas import money
from app.core.security import MemberContext, Principal, verify_password
from app.modules.ledger import service as ledger
from app.modules.members import repository as repo
from app.modules.members.models import User
from app.modules.members.schemas import BalanceOut, Me, MemberDetail, MemberSummary


def authenticate(session: Session, email: str, password: str, ip: str) -> User:
    check_login_allowed(ip, email)
    user = repo.user_by_email(session, email)
    if user is None or not verify_password(user.password_hash, password):
        raise Unauthenticated("Email or password is incorrect.", code="INVALID_CREDENTIALS")
    return user


def me(session: Session, principal: Principal) -> Me:
    user = session.get(User, principal.user_id)
    if user is None:
        raise Unauthenticated()
    summary = None
    if user.member_id is not None:
        member = repo.get_member(session, user.member_id)
        if member is not None:
            summary = MemberSummary(
                member_id=member.id,
                name=member.display_name,
                settlement_currency=member.settlement_currency,
                state=member.state,
            )
    return Me(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=principal.role,
        member=summary,
        demo_mode=get_settings().demo_mode,
    )


def member_detail(session: Session, ctx: MemberContext) -> MemberDetail:
    found = repo.get_member_with_entity(session, ctx.member_id)
    if found is None:
        raise NotFound()
    member, entity = found
    balances = [
        BalanceOut(
            currency=b.currency,
            available=money(b.available_minor, b.currency),
            held=money(b.held_minor, b.currency),
        )
        for b in ledger.member_balances(session, member.id)
    ]
    c = member.settlement_currency
    return MemberDetail(
        member_id=member.id,
        name=member.display_name,
        legal_name=entity.legal_name,
        state=member.state,
        risk_tier=member.risk_tier,
        settlement_currency=c,
        payable_limit=money(member.payable_limit_minor, c)
        if member.payable_limit_minor is not None
        else None,
        maker_checker_threshold=money(member.maker_checker_minor, c)
        if member.maker_checker_minor is not None
        else None,
        balances=balances,
    )
