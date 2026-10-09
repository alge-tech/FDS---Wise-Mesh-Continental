/** Basis points as a percentage string, with integer arithmetic only: 52 → "0.52%", 2500 → "25%". */
export function formatBps(bps: number): string {
	if (!Number.isSafeInteger(bps) || bps < 0) throw new RangeError(`Invalid basis points: ${bps}`);
	const whole = Math.trunc(bps / 100);
	const fraction = bps % 100;
	if (fraction === 0) return `${whole}%`;
	return `${whole}.${String(fraction).padStart(2, '0').replace(/0$/, '')}%`;
}
