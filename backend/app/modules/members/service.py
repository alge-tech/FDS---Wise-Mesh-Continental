from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import InvalidState, NotFound, Unauthenticated, ValidationFailed
from app.core.ratelimit import check_login_allowed
from app.core.schemas import money
from app.core.security import MemberContext, Principal, verify_password
from app.modules.audit import service as audit
from app.modules.fx.models import Currency
from app.modules.ledger import service as ledger
from app.modules.members import repository as repo
from app.modules.members.models import Member, User
from app.modules.members.schemas import (
    BalanceOut,
    Me,
    MemberDetail,
    MemberSummary,
    SettingsUpdate,
    TeamMember,
)


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
        team=[
            TeamMember(user_id=u.id, email=u.email, display_name=u.display_name, role=u.role)
            for u in repo.team(session, member.id)
        ],
    )


def update_settings(session: Session, ctx: MemberContext, body: SettingsUpdate) -> MemberDetail:
    """MC-ONB-02: the member admin edits limits, the threshold and the settlement currency.

    Limits and the threshold apply from the next computation. The settlement currency can't
    change while the member is in an unfinished run, because its statement and holds use it.
    """
    member = session.scalar(select(Member).where(Member.id == ctx.member_id).with_for_update())
    if member is None:
        raise NotFound()
    sent = body.model_fields_set - {"reason_code"}
    if not sent:
        raise ValidationFailed("Send at least one setting to change.")
    before = {
        "payable_limit_minor": member.payable_limit_minor,
        "maker_checker_minor": member.maker_checker_minor,
        "settlement_currency": member.settlement_currency,
    }
    if "settlement_currency" in sent:
        currency = body.settlement_currency
        if currency is None or session.get(Currency, currency) is None:
            raise ValidationFailed(
                "Choose a supported settlement currency.",
                details={"fields": [{"field": "settlement_currency", "reason": "unsupported"}]},
            )
        if currency != member.settlement_currency and repo.in_active_run(session, member.id):
            raise InvalidState(
                "The settlement currency can't change while a run you are in is unfinished."
            )
        member.settlement_currency = currency
    if "payable_limit_minor" in sent:
        member.payable_limit_minor = body.payable_limit_minor
    if "maker_checker_minor" in sent:
        member.maker_checker_minor = body.maker_checker_minor
    after = {
        "payable_limit_minor": member.payable_limit_minor,
        "maker_checker_minor": member.maker_checker_minor,
        "settlement_currency": member.settlement_currency,
    }
    audit.record(
        session,
        actor=ctx.principal,
        action="member.settings_changed",
        subject_type="MEMBER",
        subject_id=member.id,
        before=before,
        after=after,
        reason_code=body.reason_code,
    )
    session.flush()
    return member_detail(session, ctx)
