"""Invoice state machine (PRD "Invoice states"). Every transition is audited."""

from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import InvoiceStatus as S
from app.core.errors import InvalidState
from app.core.ids import utcnow
from app.core.security import Principal
from app.modules.audit import service as audit
from app.modules.invoices.models import Invoice

# A correction is also allowed while pending or disputed (MC-CNF-02): X -> AMENDED -> PENDING.
ALLOWED: dict[S, frozenset[S]] = {
    S.IMPORTED: frozenset({S.MATCHED, S.UNMATCHED, S.REJECTED_DATA}),
    S.MATCHED: frozenset({S.PENDING_CONFIRMATION}),
    S.UNMATCHED: frozenset({S.MATCHED}),
    S.PENDING_CONFIRMATION: frozenset({S.CONFIRMED, S.DISPUTED, S.AMENDED}),
    S.CONFIRMED: frozenset({S.LOCKED_IN_RUN, S.AMENDED, S.DISPUTED}),
    S.AMENDED: frozenset({S.PENDING_CONFIRMATION}),
    S.DISPUTED: frozenset({S.CONFIRMED, S.CANCELLED, S.AMENDED}),
    S.LOCKED_IN_RUN: frozenset({S.SETTLED_BY_NETTING, S.SETTLED_BY_TRANSFER, S.RELEASED}),
    S.RELEASED: frozenset({S.CONFIRMED}),
}
TERMINAL = frozenset({S.SETTLED_BY_NETTING, S.SETTLED_BY_TRANSFER, S.CANCELLED, S.REJECTED_DATA})
EDITABLE = frozenset({S.PENDING_CONFIRMATION, S.CONFIRMED, S.DISPUTED})


def transition(
    session: Session,
    invoice: Invoice,
    to: S,
    *,
    actor: Principal | None,
    reason_code: str | None = None,
    run_id: Any = None,
    details: dict[str, Any] | None = None,
) -> None:
    current = S(invoice.status)
    if to not in ALLOWED.get(current, frozenset()):
        raise InvalidState(
            f"An invoice can't move from {current} to {to}.",
            details={"invoice_id": str(invoice.id), "status": current},
        )
    invoice.status = to
    invoice.updated_at = utcnow()
    audit.record(
        session,
        actor=actor,
        action=f"invoice.{to.lower()}",
        subject_type="INVOICE",
        subject_id=invoice.id,
        run_id=run_id,
        before={"status": current, "version": invoice.current_version},
        after={"status": to, "version": invoice.current_version},
        reason_code=reason_code,
        details=details,
    )
