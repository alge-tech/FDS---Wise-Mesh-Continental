"""One eligibility policy shared by preview and freeze; risk screening follows freeze."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import NETTABLE_MEMBER_STATES
from app.core.enums import ExclusionReason as R
from app.core.ids import utcnow
from app.modules.confirmations.models import Confirmation
from app.modules.fx.models import FxRate
from app.modules.invoices.models import Invoice
from app.modules.members.models import KillSwitch, Member
from app.modules.netting.fx_pass import has_rate
from app.modules.windows.models import Window


@dataclass(frozen=True)
class Excluded:
    invoice: Invoice
    reason: R
    member_id: UUID | None = None


def eligible(session: Session, window: Window) -> tuple[list[Invoice], list[Excluded]]:
    members = {m.id: m for m in session.scalars(select(Member))}
    switches = list(session.scalars(select(KillSwitch).where(KillSwitch.enabled)))
    global_off = any(k.scope == "GLOBAL" for k in switches)
    blocked = {k.member_id for k in switches if k.scope == "MEMBER"}
    rates = {(r.base, r.quote): r.rate for r in session.scalars(select(FxRate))}
    confirmations: dict[tuple[UUID, int], set[UUID]] = {}
    for c in session.scalars(select(Confirmation).where(Confirmation.decision == "CONFIRMED")):
        confirmations.setdefault((c.invoice_id, c.version), set()).add(c.party_member_id)
    included: list[Invoice] = []
    excluded: list[Excluded] = []
    invoices = session.scalars(
        select(Invoice)
        .where(Invoice.status.in_(["UNMATCHED", "PENDING_CONFIRMATION", "DISPUTED", "CONFIRMED"]))
        .order_by(Invoice.id)
    )
    for i in invoices:
        reason: R | None = None
        party: UUID | None = None
        ids = (i.payer_member_id, i.issuer_member_id)
        if None in ids:
            reason = R.NOT_MATCHED
        elif i.status == "DISPUTED":
            reason = R.DISPUTED
        elif i.status != "CONFIRMED" or confirmations.get((i.id, i.current_version)) != set(ids):
            reason = R.NOT_CONFIRMED
        elif global_off:
            reason = R.KILL_SWITCH
        elif i.outstanding_minor <= 0:
            continue
        else:
            for member_id in ids:
                assert member_id is not None
                m = members[member_id]
                if m.state not in NETTABLE_MEMBER_STATES:
                    reason, party = R.MEMBER_NOT_ACTIVE, member_id
                elif member_id in blocked:
                    reason, party = R.KILL_SWITCH, member_id
                elif not m.agreement_version:
                    reason, party = R.AGREEMENT_PENDING, member_id
                elif not has_rate(rates, i.currency, m.settlement_currency):
                    reason = R.NO_RATE
                if reason:
                    break
            if (
                not reason
                and window.horizon_days is not None
                and i.due_date > (utcnow().date() + timedelta(days=window.horizon_days))
            ):
                reason = R.OUTSIDE_HORIZON
        if reason:
            excluded.append(Excluded(i, reason, party))
        else:
            included.append(i)
    return included, excluded


def public_reason(reason: R, excluded_member: UUID | None, viewer: UUID | None) -> R:
    if reason in {R.SANCTIONS_HIT, R.HOLD_FOR_REVIEW}:
        return R.UNDER_REVIEW if excluded_member == viewer else R.COUNTERPARTY_UNAVAILABLE
    if excluded_member is not None and excluded_member != viewer:
        return R.COUNTERPARTY_UNAVAILABLE
    return reason
