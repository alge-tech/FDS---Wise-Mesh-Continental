import { describe, expect, it } from 'vitest';
import { GROSS, INVOICES, NET, PAYMENTS, SAVED_PCT, netPositions } from './worked-example';

describe('landing worked example', () => {
	it('nets eight invoices into three payments into F', () => {
		expect(INVOICES).toHaveLength(8);
		expect(PAYMENTS).toEqual([
			{ from: 'A', to: 'F', amount: 40 },
			{ from: 'C', to: 'F', amount: 30 },
			{ from: 'E', to: 'F', amount: 10 }
		]);
	});

	it('keeps every net position after settlement', () => {
		const before = netPositions(INVOICES);
		const after = netPositions(PAYMENTS);
		for (const [code, value] of before) expect(after.get(code) ?? 0).toBe(value);
	});

	it('moves 82% less money', () => {
		expect([GROSS, NET, SAVED_PCT]).toEqual([450, 80, 82]);
	});
});
