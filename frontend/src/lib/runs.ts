/**
 * Plain-language run summaries. Every run screen opens with one sentence that says where the
 * run is and what happens if the reader does nothing (PRD UI rules).
 */

export interface RunSummaryInput {
	status: string;
	/** Member views only: whether this member still has a statement in the run. */
	hasStatement?: boolean;
	/** Member views only: whether this member's statement already has its approvals. */
	approved?: boolean;
}

export function runSummary({ status, hasStatement = true, approved = false }: RunSummaryInput) {
	if (!hasStatement && status !== 'COMMITTED') {
		return 'Your invoices left this run. They return to the next window; nothing moves now.';
	}
	switch (status) {
		case 'AWAITING_APPROVAL':
			return approved
				? 'You have approved. Settlement waits for the other members; if one rejects, Mesh recomputes.'
				: 'Your statement is waiting for approval. If you do nothing, settlement waits for you.';
		case 'APPROVED':
			return 'Every member has approved. Wise will hold the funds and settle; you don’t need to act.';
		case 'PREPARED':
			return 'Funds are held for settlement. Wise commits the run next; you don’t need to act.';
		case 'RECOMPUTING':
			return 'Mesh is recomputing after a change. A new statement will follow.';
		case 'COMMITTED':
			return hasStatement
				? 'Settled. Your invoices in this run are paid, and only the net amount moved.'
				: 'This run settled without your invoices; they return to the next window.';
		case 'FALLBACK_GROSS':
			return 'Netting stopped after the recompute limit. Pay these invoices gross outside Mesh.';
		case 'ABORTED':
			return 'This run was cancelled and any held funds were released. Your invoices return to the next window.';
		default:
			return 'Mesh is preparing this run. Statements follow shortly.';
	}
}

/** Admin wording for the same states, with the action ops can take next. */
export function adminRunSummary(status: string): string {
	switch (status) {
		case 'AWAITING_APPROVAL':
			return 'Waiting for member approvals. Expire approvals to remove non-responders.';
		case 'APPROVED':
			return 'All members approved. Settle to place holds and commit in one ledger entry.';
		case 'PREPARED':
			return 'Holds are placed. Settle again to commit, or abort to release every hold.';
		case 'COMMITTED':
			return 'Committed. Clearing is back to zero and every invoice has its outcome.';
		case 'FALLBACK_GROSS':
			return 'Recompute limit reached. Invoices were released for gross payment.';
		case 'ABORTED':
			return 'Aborted. Holds were released and invoices returned to the next window.';
		default:
			return 'Computing.';
	}
}

/** States in which Wise can still abort a run. */
export function canAbort(status: string): boolean {
	return !['COMMITTED', 'ABORTED', 'FALLBACK_GROSS'].includes(status);
}

/** States in which Settle has something to do (prepare, or resume to commit). */
export function canSettle(status: string): boolean {
	return status === 'APPROVED' || status === 'PREPARED';
}
