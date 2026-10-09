/**
 * Minor-unit money helpers.
 *
 * Amounts travel as integer minor units plus an ISO currency code. The number of
 * decimals (the exponent) always comes from `/v1/currencies`, never from Intl's
 * defaults. Every conversion here is integer or string arithmetic: no parseFloat,
 * no Number division, so values beyond 2^53 survive intact when passed as bigint
 * or a digit string.
 */

/** A money value as the API serialises it. */
export interface Money {
	/** Integer minor units. A JS number for API payloads; bigint or a digit string for larger values. */
	amount_minor: number | bigint | string;
	currency: string;
}

/** Largest value of a Postgres BIGINT, the storage type for every amount. */
export const MAX_MINOR = 9_223_372_036_854_775_807n;

const MAX_EXPONENT = 18;

export type MoneyParseErrorCode =
	'EMPTY' | 'INVALID_FORMAT' | 'NEGATIVE_NOT_ALLOWED' | 'TOO_MANY_DECIMALS' | 'OUT_OF_RANGE';

export class MoneyParseError extends Error {
	readonly code: MoneyParseErrorCode;

	constructor(code: MoneyParseErrorCode, message: string) {
		super(message);
		this.name = 'MoneyParseError';
		this.code = code;
	}
}

function assertExponent(exponent: number): void {
	if (!Number.isInteger(exponent) || exponent < 0 || exponent > MAX_EXPONENT) {
		throw new RangeError(`Invalid currency exponent: ${exponent}`);
	}
}

/** Normalise any accepted minor-unit representation to a bigint, rejecting non-integers. */
export function toMinorBigInt(amount: Money['amount_minor']): bigint {
	if (typeof amount === 'bigint') return amount;
	if (typeof amount === 'number') {
		if (!Number.isSafeInteger(amount)) {
			throw new RangeError(`amount_minor must be a safe integer, got ${amount}`);
		}
		return BigInt(amount);
	}
	if (!/^-?\d+$/.test(amount)) {
		throw new RangeError(`amount_minor must be an integer string, got "${amount}"`);
	}
	return BigInt(amount);
}

/**
 * Integer minor units to a plain decimal string, e.g. (-123456n, 2) → "-1234.56".
 * The result has exactly `exponent` fractional digits and no grouping.
 */
export function minorToDecimalString(amount: Money['amount_minor'], exponent: number): string {
	assertExponent(exponent);
	const minor = toMinorBigInt(amount);
	const negative = minor < 0n;
	const digits = (negative ? -minor : minor).toString();
	const sign = negative ? '-' : '';
	if (exponent === 0) return sign + digits;
	const padded = digits.padStart(exponent + 1, '0');
	const whole = padded.slice(0, padded.length - exponent);
	const fraction = padded.slice(padded.length - exponent);
	return `${sign}${whole}.${fraction}`;
}

export interface FormatMoneyOptions {
	/** 'exceptZero' shows a leading "+" on positive values (used for signed amounts). */
	signDisplay?: 'auto' | 'always' | 'exceptZero' | 'never';
	currencyDisplay?: 'symbol' | 'narrowSymbol' | 'code' | 'name';
}

const formatterCache = new Map<string, Intl.NumberFormat>();

function getFormatter(
	locale: string,
	currency: string,
	exponent: number,
	options: FormatMoneyOptions
): Intl.NumberFormat {
	const signDisplay = options.signDisplay ?? 'auto';
	const currencyDisplay = options.currencyDisplay ?? 'symbol';
	const key = [locale, currency, exponent, signDisplay, currencyDisplay].join('|');
	let formatter = formatterCache.get(key);
	if (!formatter) {
		formatter = new Intl.NumberFormat(locale, {
			style: 'currency',
			currency,
			currencyDisplay,
			signDisplay,
			// The decimal string already has exactly `exponent` digits, so Intl never rounds.
			minimumFractionDigits: exponent,
			maximumFractionDigits: exponent
		});
		formatterCache.set(key, formatter);
	}
	return formatter;
}

/**
 * Format a money value for display, e.g. ({amount_minor: 123456, currency: 'EUR'}, 2) → "€1,234.56".
 * Intl.NumberFormat receives a decimal string, which it formats exactly.
 */
export function formatMoney(
	money: Money,
	exponent: number,
	locale = 'en-GB',
	options: FormatMoneyOptions = {}
): string {
	const decimal = minorToDecimalString(money.amount_minor, exponent) as Intl.StringNumericLiteral;
	return getFormatter(locale, money.currency, exponent, options).format(decimal);
}

export interface ParseDecimalOptions {
	allowNegative?: boolean;
}

const DECIMAL_PATTERN = /^(-)?(\d+)(?:\.(\d+))?$/;

/**
 * Parse a user-typed decimal such as "1234.56" into integer minor units for the given exponent.
 * Accepts digits with an optional "." and fraction only: no grouping separators, no exponents,
 * no "+" sign. Refuses to round: more fractional digits than the exponent allows is an error.
 */
export function parseDecimalToMinor(
	input: string,
	exponent: number,
	options: ParseDecimalOptions = {}
): bigint {
	assertExponent(exponent);
	const text = input.trim();
	if (text === '') throw new MoneyParseError('EMPTY', 'Enter an amount');

	const match = DECIMAL_PATTERN.exec(text);
	if (!match) {
		throw new MoneyParseError('INVALID_FORMAT', 'Enter an amount using digits and a full stop');
	}
	const [, minus, whole, fraction = ''] = match;

	if (minus && !options.allowNegative) {
		throw new MoneyParseError('NEGATIVE_NOT_ALLOWED', 'Enter an amount greater than zero');
	}
	if (fraction.length > exponent) {
		throw new MoneyParseError(
			'TOO_MANY_DECIMALS',
			exponent === 0
				? 'This currency has no decimal places'
				: `Use at most ${exponent} decimal places`
		);
	}

	const magnitude = BigInt(whole + fraction.padEnd(exponent, '0'));
	if (magnitude > MAX_MINOR) {
		throw new MoneyParseError('OUT_OF_RANGE', 'This amount is too large');
	}
	return minus ? -magnitude : magnitude;
}

/** Convert parsed minor units to a JSON-safe number for API payloads; throws beyond 2^53. */
export function minorToSafeNumber(minor: bigint): number {
	const value = Number(minor);
	if (!Number.isSafeInteger(value)) {
		throw new RangeError('Amount exceeds the safe integer range for JSON transport');
	}
	return value;
}
