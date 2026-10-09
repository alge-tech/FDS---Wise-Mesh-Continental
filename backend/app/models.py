"""Imports every module's models so Base.metadata (and Alembic) sees all 38 tables."""

from app.modules.audit.models import AuditEvent, IdempotencyKey
from app.modules.confirmations.models import Confirmation
from app.modules.counterparties.models import Invitation
from app.modules.fx.models import Currency, FxLock, FxRate, RateSnapshot
from app.modules.invoices.models import Invoice, InvoiceVersion
from app.modules.ledger.models import JournalEntry, LedgerAccount, Posting
from app.modules.members.models import KillSwitch, LegalEntity, Member, User
from app.modules.notifications.models import Notification, OutboxEvent
from app.modules.pricing.models import FeeCharge
from app.modules.risk.models import Case, RiskDecision, SanctionsEntry
from app.modules.runs.models import (
    Cancellation,
    FxLeg,
    NetPosition,
    NettingRun,
    PlannedTransfer,
    RunComputation,
    Withdrawal,
)
from app.modules.settlement.models import Hold, InvoiceOutcome, SettlementJob
from app.modules.statements.models import Approval, Statement
from app.modules.windows.models import InvoiceExclusion, RunInvoice, Window

__all__ = [
    "Approval",
    "AuditEvent",
    "Cancellation",
    "Case",
    "Confirmation",
    "Currency",
    "FeeCharge",
    "FxLeg",
    "FxLock",
    "FxRate",
    "Hold",
    "IdempotencyKey",
    "Invitation",
    "Invoice",
    "InvoiceExclusion",
    "InvoiceOutcome",
    "InvoiceVersion",
    "JournalEntry",
    "KillSwitch",
    "LedgerAccount",
    "LegalEntity",
    "Member",
    "NetPosition",
    "NettingRun",
    "Notification",
    "OutboxEvent",
    "PlannedTransfer",
    "Posting",
    "RateSnapshot",
    "RiskDecision",
    "RunComputation",
    "RunInvoice",
    "SanctionsEntry",
    "SettlementJob",
    "Statement",
    "User",
    "Window",
    "Withdrawal",
]
