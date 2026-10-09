import { describe, expect, it } from 'vitest';
import {
	getStatusMeta,
	humaniseStatus,
	INVOICE_STATUSES,
	invoiceStatusMeta,
	isRunActive,
	RUN_STATUSES,
	runStatusMeta,
	toneClasses
} from './status';

describe('status mapping', () => {
	it('covers every invoice state from the PRD', () => {
		expect(Object.keys(invoiceStatusMeta).sort()).toEqual([...INVOICE_STATUSES].sort());
		expect(INVOICE_STATUSES).toHaveLength(13);
	});

	it('covers every run state from the PRD', () => {
		expect(Object.keys(runStatusMeta).sort()).toEqual([...RUN_STATUSES].sort());
		expect(RUN_STATUSES).toHaveLength(10);
	});

	it('gives every state a non-empty, sentence-case text label', () => {
		for (const meta of [...Object.values(invoiceStatusMeta), ...Object.values(runStatusMeta)]) {
			expect(meta.label.length).toBeGreaterThan(0);
			expect(meta.label[0]).toBe(meta.label[0].toUpperCase());
			expect(meta.label).not.toMatch(/_/);
			expect(toneClasses[meta.tone]).toBeTruthy();
		}
	});

	it('gives labels that are unique within each kind', () => {
		const invoiceLabels = Object.values(invoiceStatusMeta).map((m) => m.label);
		const runLabels = Object.values(runStatusMeta).map((m) => m.label);
		expect(new Set(invoiceLabels).size).toBe(invoiceLabels.length);
		expect(new Set(runLabels).size).toBe(runLabels.length);
	});

	it('reserves the negative tone for disputes and errors', () => {
		const negative = [
			...Object.entries(invoiceStatusMeta),
			...Object.entries(runStatusMeta)
		].filter(([, meta]) => meta.tone === 'negative');
		expect(negative.map(([status]) => status).sort()).toEqual([
			'ABORTED',
			'DISPUTED',
			'REJECTED_DATA'
		]);
	});

	it('maps known states', () => {
		expect(getStatusMeta('invoice', 'PENDING_CONFIRMATION')).toEqual({
			label: 'Awaiting confirmation',
			tone: 'pending'
		});
		expect(getStatusMeta('invoice', 'SETTLED_BY_NETTING').tone).toBe('positive');
		expect(getStatusMeta('run', 'COMMITTED')).toEqual({ label: 'Settled', tone: 'positive' });
		expect(getStatusMeta('run', 'AWAITING_APPROVAL').tone).toBe('pending');
	});

	it('does not cross invoice and run maps', () => {
		expect(getStatusMeta('run', 'DISPUTED')).toEqual({ label: 'Disputed', tone: 'neutral' });
	});

	it('falls back to a humanised neutral label for unknown states', () => {
		expect(getStatusMeta('run', 'HOLD_FOR_REVIEW')).toEqual({
			label: 'Hold for review',
			tone: 'neutral'
		});
		expect(getStatusMeta('invoice', 'toString').tone).toBe('neutral');
		expect(humaniseStatus('NEW_STATE')).toBe('New state');
	});

	it('knows which runs are still active', () => {
		expect(isRunActive('AWAITING_APPROVAL')).toBe(true);
		expect(isRunActive('RECOMPUTING')).toBe(true);
		expect(isRunActive('COMMITTED')).toBe(false);
		expect(isRunActive('ABORTED')).toBe(false);
		expect(isRunActive('FALLBACK_GROSS')).toBe(false);
	});
});
