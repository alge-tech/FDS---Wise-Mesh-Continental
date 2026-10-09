import { describe, expect, it } from 'vitest';
import { formatBps } from './bps';

describe('formatBps', () => {
	it('formats whole and fractional percentages exactly', () => {
		expect(formatBps(2500)).toBe('25%');
		expect(formatBps(52)).toBe('0.52%');
		expect(formatBps(150)).toBe('1.5%');
		expect(formatBps(10_000)).toBe('100%');
		expect(formatBps(0)).toBe('0%');
		expect(formatBps(5)).toBe('0.05%');
	});

	it('rejects values that are not whole basis points', () => {
		expect(() => formatBps(1.5)).toThrow(RangeError);
		expect(() => formatBps(-1)).toThrow(RangeError);
	});
});
