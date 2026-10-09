from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import transaction
from app.core.security import Principal
from app.modules.audit import service as audit
from app.modules.demo.seed import seed, truncate_all


def reset(session: Session, actor: Principal) -> dict[str, Any]:
    """Wipe and re-seed. Truncation needs the owner role; the seed runs as the app role."""
    owner = create_engine(get_settings().migration_database_url)
    try:
        with Session(owner) as owner_session, owner_session.begin():
            truncate_all(owner_session)
    finally:
        owner.dispose()
    with transaction(session):
        seed(session)
        audit.record(
            session,
            actor=None,
            action="demo.reset",
            subject_type="SYSTEM",
            subject_id=actor.user_id,
            reason_code="DEMO_RESET",
            details={"requested_by_role": actor.role},
        )
    return {"ok": True}
