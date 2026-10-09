/**
 * Invoice and run states → label text plus a colour tone.
 * Every chip shows its label, so status is never conveyed by colour alone (WCAG 1.4.1).
 */

export type StatusTone = 'neutral' | 'pending' | 'active' | 'positive' | 'negative';

export interface StatusMeta {
	label: string;
	tone: StatusTone;
}

export const INVOICE_STATUSES = [
	'IMPORTED',
	'MATCHED',
	'UNMATCHED',
	'PENDING_CONFIRMATION',
	'CONFIRMED',
	'AMENDED',
	'DISPUTED',
	'LOCKED_IN_RUN',
	'RELEASED',
	'SETTLED_BY_NETTING',
	'SETTLED_BY_TRANSFER',
	'CANCELLED',
	'REJECTED_DATA'
] as const;
export type InvoiceStatus = (typeof INVOICE_STATUSES)[number];

export const RUN_STATUSES = [
	'FROZEN',
	'SCREENED',
	'COMPUTED',
	'AWAITING_APPROVAL',
	'APPROVED',
	'PREPARED',
	'COMMITTED',
	'RECOMPUTING',
	'FALLBACK_GROSS',
	'ABORTED'
] as const;
export type RunStatus = (typeof RUN_STATUSES)[number];

export const invoiceStatusMeta: Record<InvoiceStatus, StatusMeta> = {
	IMPORTED: { label: 'Imported', tone: 'neutral' },
	MATCHED: { label: 'Matched', tone: 'neutral' },
	UNMATCHED: { label: 'Unmatched', tone: 'pending' },
	PENDING_CONFIRMATION: { label: 'Awaiting confirmation', tone: 'pending' },
	CONFIRMED: { label: 'Confirmed', tone: 'positive' },
	AMENDED: { label: 'Amended', tone: 'pending' },
	DISPUTED: { label: 'Disputed', tone: 'negative' },
	LOCKED_IN_RUN: { label: 'In netting run', tone: 'active' },
	RELEASED: { label: 'Released', tone: 'neutral' },
	SETTLED_BY_NETTING: { label: 'Settled by netting', tone: 'positive' },
	SETTLED_BY_TRANSFER: { label: 'Settled by transfer', tone: 'positive' },
	CANCELLED: { label: 'Cancelled', tone: 'neutral' },
	REJECTED_DATA: { label: 'Rejected: data errors', tone: 'negative' }
};

export const runStatusMeta: Record<RunStatus, StatusMeta> = {
	FROZEN: { label: 'Frozen', tone: 'active' },
	SCREENED: { label: 'Screened', tone: 'active' },
	COMPUTED: { label: 'Computed', tone: 'active' },
	AWAITING_APPROVAL: { label: 'Awaiting approval', tone: 'pending' },
	APPROVED: { label: 'Approved', tone: 'active' },
	PREPARED: { label: 'Funds held', tone: 'active' },
	COMMITTED: { label: 'Settled', tone: 'positive' },
	RECOMPUTING: { label: 'Recomputing', tone: 'pending' },
	FALLBACK_GROSS: { label: 'Fell back to gross', tone: 'pending' },
	ABORTED: { label: 'Aborted', tone: 'negative' }
};

/** Token classes per tone. Negative is reserved for errors and disputes, never ordinary payables. */
export const toneClasses: Record<StatusTone, string> = {
	neutral: 'bg-background-neutral text-content-primary',
	pending: 'bg-sentiment-warning text-content-primary',
	active: 'bg-brand-primary text-brand-forest',
	positive: 'bg-brand-pale text-sentiment-positive',
	negative: 'bg-sentiment-negative text-background-screen'
};

export type StatusKind = 'invoice' | 'run';

/** "SOME_NEW_STATE" → "Some new state", for states the frontend does not know yet. */
export function humaniseStatus(status: string): string {
	const words = status.toLowerCase().replaceAll('_', ' ').trim();
	return words.charAt(0).toUpperCase() + words.slice(1);
}

function hasKey<K extends string>(map: Record<K, StatusMeta>, key: string): key is K {
	return Object.hasOwn(map, key);
}

export function getStatusMeta(kind: StatusKind, status: string): StatusMeta {
	const map: Record<string, StatusMeta> = kind === 'invoice' ? invoiceStatusMeta : runStatusMeta;
	if (hasKey(map, status)) return map[status];
	return { label: humaniseStatus(status), tone: 'neutral' };
}

/** Runs in these states are still moving; run and statement screens poll while active. */
export const ACTIVE_RUN_STATUSES: ReadonlySet<RunStatus> = new Set([
	'FROZEN',
	'SCREENED',
	'COMPUTED',
	'AWAITING_APPROVAL',
	'APPROVED',
	'PREPARED',
	'RECOMPUTING'
]);

export function isRunActive(status: string): boolean {
	return (ACTIVE_RUN_STATUSES as ReadonlySet<string>).has(status);
}
