"""The invoice state machine matches the PRD's "Invoice states" table."""

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from app.core.enums import InvoiceStatus as S
from app.core.errors import InvalidState
from app.modules.invoices import state

# PRD "Invoice states", verbatim.
PRD: dict[S, set[S]] = {
    S.IMPORTED: {S.MATCHED, S.UNMATCHED, S.REJECTED_DATA},
    S.MATCHED: {S.PENDING_CONFIRMATION},
    S.UNMATCHED: {S.MATCHED},
    S.PENDING_CONFIRMATION: {S.CONFIRMED, S.DISPUTED},
    S.CONFIRMED: {S.LOCKED_IN_RUN, S.AMENDED, S.DISPUTED},
    S.AMENDED: {S.PENDING_CONFIRMATION},
    S.DISPUTED: {S.CONFIRMED, S.CANCELLED},
    S.LOCKED_IN_RUN: {S.SETTLED_BY_NETTING, S.SETTLED_BY_TRANSFER, S.RELEASED},
    S.RELEASED: {S.CONFIRMED},
}
PRD_TERMINAL = {S.SETTLED_BY_NETTING, S.SETTLED_BY_TRANSFER, S.CANCELLED, S.REJECTED_DATA}
# MC-CNF-02 lets either party propose a correction while pending or disputed.
DOCUMENTED_EXTRAS = {(S.PENDING_CONFIRMATION, S.AMENDED), (S.DISPUTED, S.AMENDED)}


def test_every_status_is_either_transitional_or_terminal() -> None:
    assert set(state.ALLOWED) | state.TERMINAL == set(S)
    assert not set(state.ALLOWED) & state.TERMINAL
    assert state.TERMINAL == PRD_TERMINAL


def test_transitions_match_the_prd_plus_documented_corrections() -> None:
    code = {(a, b) for a, targets in state.ALLOWED.items() for b in targets}
    prd = {(a, b) for a, targets in PRD.items() for b in targets}
    assert prd <= code
    assert code - prd == DOCUMENTED_EXTRAS


def test_editable_states_can_all_be_amended() -> None:
    assert all(S.AMENDED in state.ALLOWED[s] for s in state.EDITABLE)


def test_terminal_states_are_reachable() -> None:
    reachable = {S.IMPORTED}
    frontier = [S.IMPORTED]
    while frontier:
        for nxt in state.ALLOWED.get(frontier.pop(), frozenset()):
            if nxt not in reachable:
                reachable.add(nxt)
                frontier.append(nxt)
    assert reachable == set(S)


def invoice(status: S) -> Any:
    return SimpleNamespace(id=uuid4(), status=status, current_version=1, updated_at=None)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.SETTLED_BY_NETTING, S.CONFIRMED),
        (S.CANCELLED, S.CONFIRMED),
        (S.LOCKED_IN_RUN, S.CONFIRMED),  # must go through RELEASED
        (S.PENDING_CONFIRMATION, S.LOCKED_IN_RUN),
        (S.IMPORTED, S.CONFIRMED),
    ],
)
def test_illegal_transition_raises_and_leaves_the_invoice_alone(current: S, target: S) -> None:
    inv = invoice(current)
    with pytest.raises(InvalidState) as exc:
        state.transition(None, inv, target, actor=None)  # type: ignore[arg-type]
    assert inv.status == current and inv.updated_at is None
    assert exc.value.details["status"] == current


def test_legal_transition_updates_status_and_audits(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(state.audit, "record", lambda _s, **kw: recorded.append(kw))
    inv = invoice(S.LOCKED_IN_RUN)
    state.transition(None, inv, S.RELEASED, actor=None, reason_code="RUN_ABORTED")  # type: ignore[arg-type]
    assert inv.status == S.RELEASED and inv.updated_at is not None
    [event] = recorded
    assert event["action"] == "invoice.released"
    assert event["before"]["status"] == S.LOCKED_IN_RUN
    assert event["after"]["status"] == S.RELEASED
    assert event["reason_code"] == "RUN_ABORTED"
