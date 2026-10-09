import { describe, expect, it } from 'vitest';
import { adminRunSummary, canAbort, canSettle, runSummary } from './runs';

describe('run summaries', () => {
	it('tells a member what happens if they do nothing', () => {
		expect(runSummary({ status: 'AWAITING_APPROVAL' })).toContain('If you do nothing');
		expect(runSummary({ status: 'AWAITING_APPROVAL', approved: true })).toContain('other members');
		expect(runSummary({ status: 'PREPARED' })).toContain('Funds are held');
		expect(runSummary({ status: 'COMMITTED' })).toContain('Settled');
	});

	it('explains an exclusion without naming a reason', () => {
		expect(runSummary({ status: 'AWAITING_APPROVAL', hasStatement: false })).toContain(
			'left this run'
		);
		expect(runSummary({ status: 'COMMITTED', hasStatement: false })).toContain('without your');
	});

	it('gives ops the next action', () => {
		expect(adminRunSummary('APPROVED')).toContain('Settle');
		expect(adminRunSummary('PREPARED')).toContain('abort');
	});

	it('only offers settle and abort where they apply', () => {
		expect(canSettle('APPROVED')).toBe(true);
		expect(canSettle('PREPARED')).toBe(true);
		expect(canSettle('AWAITING_APPROVAL')).toBe(false);
		expect(canAbort('PREPARED')).toBe(true);
		expect(canAbort('COMMITTED')).toBe(false);
	});
});
