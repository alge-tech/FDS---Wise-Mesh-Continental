import { describe, expect, it } from 'vitest';
import {
	formatMoney,
	MAX_MINOR,
	minorToDecimalString,
	minorToSafeNumber,
	MoneyParseError,
	parseDecimalToMinor,
	toMinorBigInt
} from './money';

function parseError(fn: () => unknown): MoneyParseError {
	try {
		fn();
	} catch (error) {
		if (error instanceof MoneyParseError) return error;
		throw error;
	}
	throw new Error('expected a MoneyParseError');
}

describe('minorToDecimalString', () => {
	it.each([
		[123456, 2, '1234.56'],
		[5, 2, '0.05'],
		[0, 2, '0.00'],
		[-5, 2, '-0.05'],
		[-123456, 2, '-1234.56'],
		[123456, 0, '123456'],
		[-7, 0, '-7'],
		[0, 0, '0'],
		[123456, 3, '123.456'],
		[7, 3, '0.007'],
		[-1000, 3, '-1.000']
	])('(%s, exponent %s) → %s', (minor, exponent, expected) => {
		expect(minorToDecimalString(minor, exponent)).toBe(expected);
	});

	it('keeps every digit beyond 2^53', () => {
		expect(minorToDecimalString(9_007_199_254_740_993n, 2)).toBe('90071992547409.93');
		expect(minorToDecimalString('-9007199254740993', 2)).toBe('-90071992547409.93');
		expect(minorToDecimalString(MAX_MINOR, 2)).toBe('92233720368547758.07');
	});

	it('rejects non-integer and unsafe inputs', () => {
		expect(() => minorToDecimalString(1.5, 2)).toThrow(RangeError);
		expect(() => minorToDecimalString(2 ** 53, 2)).toThrow(RangeError);
		expect(() => minorToDecimalString('12.5', 2)).toThrow(RangeError);
		expect(() => minorToDecimalString(1, -1)).toThrow(RangeError);
		expect(() => minorToDecimalString(1, 2.5)).toThrow(RangeError);
	});
});

describe('formatMoney', () => {
	it('formats exponent 2 currencies', () => {
		expect(formatMoney({ amount_minor: 123456, currency: 'EUR' }, 2)).toBe('€1,234.56');
		expect(formatMoney({ amount_minor: 4_000_000, currency: 'GBP' }, 2)).toBe('£40,000.00');
		expect(formatMoney({ amount_minor: 1, currency: 'USD' }, 2)).toBe('US$0.01');
	});

	it('uses the served exponent, not Intl defaults', () => {
		// Intl's default for HUF is 2 and for JPY 0; the served exponent wins either way.
		expect(formatMoney({ amount_minor: 123456, currency: 'HUF' }, 0)).toBe('HUF\u00a0123,456');
		expect(formatMoney({ amount_minor: 123456, currency: 'JPY' }, 2)).toBe('JP¥1,234.56');
	});

	it('formats exponent 0 and exponent 3 currencies', () => {
		expect(formatMoney({ amount_minor: 1500, currency: 'JPY' }, 0)).toBe('JP¥1,500');
		expect(formatMoney({ amount_minor: 1_234_567, currency: 'KWD' }, 3)).toBe('KWD\u00a01,234.567');
		expect(formatMoney({ amount_minor: 5, currency: 'BHD' }, 3)).toBe('BHD\u00a00.005');
	});

	it('formats negatives', () => {
		expect(formatMoney({ amount_minor: -123456, currency: 'EUR' }, 2)).toBe('-€1,234.56');
		expect(formatMoney({ amount_minor: -5, currency: 'EUR' }, 2)).toBe('-€0.05');
		expect(formatMoney({ amount_minor: -1500, currency: 'JPY' }, 0)).toBe('-JP¥1,500');
	});

	it('shows a plus sign for signed positive amounts', () => {
		const options = { signDisplay: 'exceptZero' } as const;
		expect(formatMoney({ amount_minor: 2500, currency: 'EUR' }, 2, 'en-GB', options)).toBe(
			'+€25.00'
		);
		expect(formatMoney({ amount_minor: 0, currency: 'EUR' }, 2, 'en-GB', options)).toBe('€0.00');
		expect(formatMoney({ amount_minor: -2500, currency: 'EUR' }, 2, 'en-GB', options)).toBe(
			'-€25.00'
		);
	});

	it('formats values beyond 2^53 exactly', () => {
		expect(formatMoney({ amount_minor: 9_007_199_254_740_993n, currency: 'EUR' }, 2)).toBe(
			'€90,071,992,547,409.93'
		);
		expect(formatMoney({ amount_minor: -MAX_MINOR, currency: 'EUR' }, 2)).toBe(
			'-€92,233,720,368,547,758.07'
		);
		expect(formatMoney({ amount_minor: '123456789012345678', currency: 'EUR' }, 3)).toBe(
			'€123,456,789,012,345.678'
		);
	});

	it('honours the locale', () => {
		expect(formatMoney({ amount_minor: 123456, currency: 'EUR' }, 2, 'de-DE')).toBe(
			'1.234,56\u00a0€'
		);
	});
});

describe('parseDecimalToMinor', () => {
	it.each([
		['1234.56', 2, 123456n],
		['1234.5', 2, 123450n],
		['1234', 2, 123400n],
		['0.01', 2, 1n],
		['  42.10 ', 2, 4210n],
		['007.50', 2, 750n],
		['1500', 0, 1500n],
		['1.234', 3, 1234n],
		['0.5', 3, 500n]
	])('"%s" with exponent %s → %s', (input, exponent, expected) => {
		expect(parseDecimalToMinor(input, exponent)).toBe(expected);
	});

	it('round-trips with minorToDecimalString', () => {
		for (const [minor, exponent] of [
			[123456n, 2],
			[1n, 3],
			[987654321n, 0],
			[MAX_MINOR, 2]
		] as const) {
			expect(parseDecimalToMinor(minorToDecimalString(minor, exponent), exponent)).toBe(minor);
		}
	});

	it('parses values beyond 2^53 exactly', () => {
		expect(parseDecimalToMinor('90071992547409.93', 2)).toBe(9_007_199_254_740_993n);
		expect(parseDecimalToMinor('92233720368547758.07', 2)).toBe(MAX_MINOR);
	});

	it('refuses to round over-precise input', () => {
		expect(parseError(() => parseDecimalToMinor('1.005', 2)).code).toBe('TOO_MANY_DECIMALS');
		expect(parseError(() => parseDecimalToMinor('1.500', 2)).code).toBe('TOO_MANY_DECIMALS');
		expect(parseError(() => parseDecimalToMinor('10.5', 0)).code).toBe('TOO_MANY_DECIMALS');
		expect(parseError(() => parseDecimalToMinor('10.0', 0)).code).toBe('TOO_MANY_DECIMALS');
		expect(parseError(() => parseDecimalToMinor('0.0001', 3)).code).toBe('TOO_MANY_DECIMALS');
	});

	it.each([
		'1e3',
		'1E-2',
		'1,234.56',
		'1 234',
		'.5',
		'5.',
		'+5',
		'abc',
		'0x10',
		'1.2.3',
		'Infinity'
	])('rejects "%s" as invalid format', (input) => {
		expect(parseError(() => parseDecimalToMinor(input, 2)).code).toBe('INVALID_FORMAT');
	});

	it('rejects empty input', () => {
		expect(parseError(() => parseDecimalToMinor('   ', 2)).code).toBe('EMPTY');
	});

	it('rejects negatives unless allowed', () => {
		expect(parseError(() => parseDecimalToMinor('-1.00', 2)).code).toBe('NEGATIVE_NOT_ALLOWED');
		expect(parseDecimalToMinor('-1.25', 2, { allowNegative: true })).toBe(-125n);
	});

	it('rejects amounts beyond BIGINT', () => {
		expect(parseError(() => parseDecimalToMinor('92233720368547758.08', 2)).code).toBe(
			'OUT_OF_RANGE'
		);
	});
});

describe('toMinorBigInt and minorToSafeNumber', () => {
	it('converts between representations', () => {
		expect(toMinorBigInt(42)).toBe(42n);
		expect(toMinorBigInt('-42')).toBe(-42n);
		expect(minorToSafeNumber(123456n)).toBe(123456);
		expect(() => minorToSafeNumber(9_007_199_254_740_993n)).toThrow(RangeError);
	});
});
