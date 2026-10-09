"""Member reads. Every member-facing function takes the caller's member_id (layering rule 3)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import KillSwitchScope
from app.modules.members.models import KillSwitch, LegalEntity, Member, User


def get_member(session: Session, member_id: UUID) -> Member | None:
    return session.get(Member, member_id)


def get_member_with_entity(session: Session, member_id: UUID) -> tuple[Member, LegalEntity] | None:
    row = session.execute(
        select(Member, LegalEntity)
        .join(LegalEntity, LegalEntity.id == Member.legal_entity_id)
        .where(Member.id == member_id)
    ).one_or_none()
    return (row[0], row[1]) if row else None


def team(session: Session, member_id: UUID) -> list[User]:
    return list(
        session.scalars(select(User).where(User.member_id == member_id).order_by(User.email))
    )


def user_by_email(session: Session, email: str) -> User | None:
    return session.scalars(select(User).where(User.email == email.strip().lower())).one_or_none()


def kill_switch_on(session: Session, member_id: UUID | None = None) -> bool:
    """Global switch, or the member's switch when member_id is given."""
    query = select(KillSwitch.enabled).where(KillSwitch.scope == KillSwitchScope.GLOBAL)
    if member_id is not None:
        query = select(KillSwitch.enabled).where(
            KillSwitch.scope == KillSwitchScope.MEMBER, KillSwitch.member_id == member_id
        )
    return bool(session.scalar(query))
