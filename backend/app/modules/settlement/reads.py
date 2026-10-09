"""Settlement reads: the member's own side (Mesh settlement only) and the staff detail."""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import (
    TERMINAL_RUN_STATES,
    HoldStatus,
    InvoiceOutcomeKind,
    JournalKind,
    LedgerAccountType,
    PartyType,
    RunStatus,
)
from app.core.ids import utcnow
from app.core.schemas import money
from app.modules.ledger import service as ledger
from app.modules.ledger.models import JournalEntry, LedgerAccount, Posting
from app.modules.members.models import Member
from app.modules.runs import repository
from app.modules.runs.models import NettingRun, PlannedTransfer
from app.modules.settlement.models import Hold, InvoiceOutcome, SettlementJob
from app.modules.settlement.schemas import (
    AccountBalance,
    ClearingBreak,
    HoldView,
    JobView,
    LedgerCheck,
    LedgerLine,
    MemberSettlement,
    SettlementDetail,
    TransferView,
)
from app.modules.statements import content as statement_content
from app.modules.statements.models import Statement

_ACCOUNT = {
    LedgerAccountType.MEMBER_BALANCE: "BALANCE",
    LedgerAccountType.MEMBER_HOLD: "HELD",
    LedgerAccountType.SUSPENSE: "CARRIED",
}


def _describe(kind: str, account: str, amount: int) -> str:
    if kind == JournalKind.HOLD:
        return "Held for settlement" if account == "HELD" else "Moved to held for settlement"
    if kind == JournalKind.RELEASE:
        return "Hold released" if account == "HELD" else "Returned from hold"
    if account == "CARRIED":
        return "Carried to the next window" if amount > 0 else "Carried in from an earlier window"
    return "Received from Mesh settlement" if amount > 0 else "Paid to Mesh settlement"


def reference(run: NettingRun) -> str:
    return f"MESH-{run.id.hex[-10:].upper()}"


def member_settlement(
    session: Session, run: NettingRun, member_id: UUID, statement: Statement | None
) -> MemberSettlement | None:
    """The member's debit or credit with Mesh settlement, its hold and its own postings."""
    if statement is None:
        return None
    c = statement.content
    currency = statement_content.settlement_currency(c)
    debit, credit = statement_content.debit_credit(c)
    status = {
        RunStatus.COMMITTED: "SETTLED",
        RunStatus.PREPARED: "FUNDS_HELD",
        RunStatus.ABORTED: "CANCELLED",
        RunStatus.FALLBACK_GROSS: "CANCELLED",
    }.get(RunStatus(run.status), "PENDING")
    hold = session.scalar(
        select(Hold).where(
            Hold.run_id == run.id, Hold.member_id == member_id, Hold.status == HoldStatus.ACTIVE
        )
    )
    own = list(statement_content.invoice_ids(c))
    counts = dict(
        session.execute(
            select(InvoiceOutcome.outcome, func.count())
            .where(InvoiceOutcome.run_id == run.id, InvoiceOutcome.invoice_id.in_(own))
            .group_by(InvoiceOutcome.outcome)
        )
        .tuples()
        .all()
    )
    rows = session.execute(
        select(
            JournalEntry.kind,
            JournalEntry.seq,
            JournalEntry.created_at,
            LedgerAccount.type,
            Posting.currency,
            func.sum(Posting.amount_minor),
        )
        .join(Posting, Posting.journal_entry_id == JournalEntry.id)
        .join(LedgerAccount, LedgerAccount.id == Posting.account_id)
        .where(JournalEntry.run_id == run.id, LedgerAccount.member_id == member_id)
        .group_by(
            JournalEntry.kind,
            JournalEntry.seq,
            JournalEntry.created_at,
            LedgerAccount.type,
            Posting.currency,
        )
        .order_by(JournalEntry.seq, LedgerAccount.type)
    ).tuples()
    lines = []
    for kind, _, created_at, account_type, line_currency, total in rows:
        amount = int(total)
        if amount == 0 or account_type not in _ACCOUNT:
            continue
        account = _ACCOUNT[LedgerAccountType(account_type)]
        lines.append(
            LedgerLine(
                entry_kind=kind,
                account=account,
                description=_describe(kind, account, amount),
                amount=money(amount, line_currency),
                created_at=created_at,
            )
        )
    carried = int(c.get("carried_minor", 0))
    return MemberSettlement(
        status=status,
        instruction="DEBIT" if debit else "CREDIT" if credit else "NONE",
        amount=money(debit or credit, currency),
        reference=reference(run),
        held=money(hold.amount_minor, hold.currency) if hold else None,
        carried=money(carried, currency) if carried else None,
        settled_by_netting=int(counts.get(InvoiceOutcomeKind.SETTLED_BY_NETTING, 0)),
        settled_by_transfer=int(counts.get(InvoiceOutcomeKind.SETTLED_BY_TRANSFER, 0)),
        ledger=lines,
    )


def _names(session: Session) -> dict[UUID, str]:
    return dict(session.execute(select(Member.id, Member.display_name)).tuples().all())


def _party(names: dict[UUID, str], party: str, member_id: UUID | None) -> str:
    if party == PartyType.FX:
        return "Mesh FX"
    if party == PartyType.CARRY:
        return "Carry forward"
    return names.get(member_id, "Unknown member") if member_id else "Unknown member"


def settlement_detail(session: Session, run: NettingRun) -> SettlementDetail:
    names = _names(session)
    computation = repository.latest(session, run)
    transfers = (
        [
            TransferView(
                payer=_party(names, t.payer_party, t.payer_member_id),
                receiver=_party(names, t.receiver_party, t.receiver_member_id),
                currency=t.currency,
                amount_minor=t.amount_minor,
                kind=t.kind,
                status=t.status,
            )
            for t in session.scalars(
                select(PlannedTransfer)
                .where(PlannedTransfer.computation_id == computation.id)
                .order_by(PlannedTransfer.currency, PlannedTransfer.amount_minor.desc())
            )
        ]
        if computation
        else []
    )
    return SettlementDetail(
        holds=[
            HoldView(
                member_id=h.member_id,
                member_name=names.get(h.member_id, ""),
                currency=h.currency,
                amount_minor=h.amount_minor,
                status=h.status,
            )
            for h in session.scalars(
                select(Hold).where(Hold.run_id == run.id).order_by(Hold.created_at, Hold.id)
            )
        ],
        jobs=[
            JobView.model_validate(j)
            for j in session.scalars(
                select(SettlementJob)
                .where(SettlementJob.run_id == run.id)
                .order_by(SettlementJob.created_at, SettlementJob.id)
            )
        ],
        transfers=transfers,
        clearing=[
            AccountBalance(currency=currency, balance_minor=amount)
            for (_, currency), amount in sorted(
                ledger.run_account_balances(session, run.id, LedgerAccountType.CLEARING).items(),
                key=lambda item: item[0][1],
            )
        ],
        commit_entry_seq=session.scalar(
            select(JournalEntry.seq).where(
                JournalEntry.run_id == run.id, JournalEntry.kind == JournalKind.COMMIT
            )
        ),
    )


def ledger_check(session: Session) -> LedgerCheck:
    """MC-LED-02 hash chain, plus every run's clearing at zero and no hold left on a closed run."""
    report = ledger.check_chain(session)
    closed = {
        run_id
        for run_id, status in session.execute(select(NettingRun.id, NettingRun.status)).tuples()
        if status in TERMINAL_RUN_STATES
    }
    totals: dict[tuple[UUID, str, str], int] = defaultdict(int)
    for run_id, account_type, currency, amount in session.execute(
        select(
            LedgerAccount.run_id,
            LedgerAccount.type,
            Posting.currency,
            func.sum(Posting.amount_minor),
        )
        .join(Posting, Posting.account_id == LedgerAccount.id)
        .where(
            LedgerAccount.run_id.is_not(None),
            LedgerAccount.type.in_([LedgerAccountType.CLEARING, LedgerAccountType.MEMBER_HOLD]),
        )
        .group_by(LedgerAccount.run_id, LedgerAccount.type, Posting.currency)
    ).tuples():
        if run_id is not None:
            totals[(run_id, account_type, currency)] += int(amount)
    breaks = [
        ClearingBreak(run_id=run_id, account_type=kind, currency=currency, balance_minor=amount)
        for (run_id, kind, currency), amount in sorted(totals.items(), key=lambda i: str(i[0]))
        if amount and (kind == LedgerAccountType.CLEARING or run_id in closed)
    ]
    active = int(
        session.scalar(
            select(func.count()).select_from(Hold).where(Hold.status == HoldStatus.ACTIVE)
        )
        or 0
    )
    return LedgerCheck(
        ok=report.ok and not breaks,
        entries=report.entries,
        chain_ok=report.ok,
        first_break_seq=report.first_break_seq,
        unbalanced_entries=report.unbalanced_entries,
        clearing_ok=not breaks,
        breaks=breaks,
        active_holds=active,
        checked_at=utcnow(),
    )
