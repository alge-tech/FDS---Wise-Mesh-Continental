from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.runs.models import NettingRun, RunComputation
from app.modules.statements.models import Statement
from app.modules.windows.models import RunInvoice


def get_for_member(session: Session, member_id: UUID, run_id: UUID) -> NettingRun | None:
    participation = select(RunInvoice.run_id).where(
        (RunInvoice.payer_member_id == member_id) | (RunInvoice.receiver_member_id == member_id)
    )
    return session.scalar(
        select(NettingRun).where(NettingRun.id == run_id, NettingRun.id.in_(participation))
    )


def list_for_member(session: Session, member_id: UUID) -> list[NettingRun]:
    participation = select(RunInvoice.run_id).where(
        (RunInvoice.payer_member_id == member_id) | (RunInvoice.receiver_member_id == member_id)
    )
    return list(
        session.scalars(
            select(NettingRun)
            .where(NettingRun.id.in_(participation))
            .order_by(NettingRun.started_at.desc())
        )
    )


def latest(session: Session, run: NettingRun) -> RunComputation | None:
    return session.scalar(
        select(RunComputation).where(
            RunComputation.run_id == run.id, RunComputation.attempt == run.current_attempt
        )
    )


def statement_for_member(session: Session, member_id: UUID, statement_id: UUID) -> Statement | None:
    return session.scalar(
        select(Statement).where(Statement.id == statement_id, Statement.member_id == member_id)
    )
