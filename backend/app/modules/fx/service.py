"""FX rate locks (MC-FX-03). Rates are locked when a run is approved, with an expiry.

Settlement re-checks the locks of the current computation in prepare and again in
commit; an expired lock aborts the run so its invoices are re-priced in the next window.
"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ids import utcnow
from app.modules.fx.models import FxLock
from app.modules.runs.models import FxLeg


def lock_rates(session: Session, run_id: UUID, computation_id: UUID) -> list[FxLock]:
    expires_at = utcnow() + timedelta(minutes=get_settings().fx_lock_minutes)
    locks = [
        FxLock(
            run_id=run_id,
            member_id=leg.member_id,
            base=leg.from_currency,
            quote=leg.to_currency,
            rate=leg.rate,
            expires_at=expires_at,
        )
        for leg in session.scalars(
            select(FxLeg)
            .where(FxLeg.computation_id == computation_id)
            .order_by(FxLeg.member_id, FxLeg.from_currency)
        )
    ]
    session.add_all(locks)
    session.flush()
    return locks


def current_locks(session: Session, run_id: UUID, since: datetime) -> list[FxLock]:
    """Locks taken for the current computation (created when it was approved)."""
    return list(
        session.scalars(
            select(FxLock)
            .where(FxLock.run_id == run_id, FxLock.created_at >= since)
            .order_by(FxLock.created_at, FxLock.id)
        )
    )


def expired(locks: list[FxLock]) -> list[FxLock]:
    now = utcnow()
    return [lock for lock in locks if lock.expires_at <= now]
