"""Rebuild what settlement needs from the stored computation (no engine re-run).

Prepare and commit work from the rows the computation persisted: net positions (members,
FX and CARRY parties), the dust carries in its metrics, and the fee charges. The ledger's
pure posting builders take this plan exactly as they take an EngineResult.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import PartyType
from app.modules.netting.types import Carry
from app.modules.netting.types import NetPosition as EnginePosition
from app.modules.pricing.models import FeeCharge
from app.modules.runs.models import NetPosition, RunComputation


@dataclass(frozen=True)
class StoredPlan:
    positions: tuple[EnginePosition, ...]
    carries: tuple[Carry, ...]
    carry_in_used: tuple[Carry, ...]
    fees: dict[UUID, int]

    def position_of(self, member_id: UUID) -> EnginePosition | None:
        return next((p for p in self.positions if p.member_id == member_id), None)


def _carries(raw: object) -> tuple[Carry, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        Carry(UUID(str(c["member_id"])), str(c["currency"]), int(c["amount_minor"])) for c in raw
    )


def load(session: Session, computation: RunComputation) -> StoredPlan:
    carries = _carries(computation.metrics.get("carries"))
    carried = {(c.member_id, c.currency): c.amount_minor for c in carries}
    rows = session.scalars(
        select(NetPosition)
        .where(NetPosition.computation_id == computation.id)
        .order_by(NetPosition.currency, NetPosition.party_type, NetPosition.member_id)
    )
    positions = tuple(
        EnginePosition(
            PartyType(r.party_type),
            r.member_id,
            r.currency,
            r.amount_minor,
            carried.get((r.member_id, r.currency), 0) if r.member_id else 0,
            r.gross_in_minor,
            r.gross_out_minor,
        )
        for r in rows
    )
    fees = {
        f.member_id: f.fee_minor
        for f in session.scalars(
            select(FeeCharge).where(FeeCharge.computation_id == computation.id)
        )
    }
    return StoredPlan(positions, carries, _carries(computation.metrics.get("carry_in_used")), fees)
