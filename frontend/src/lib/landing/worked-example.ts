/**
 * The worked example drawn on the landing page. It mirrors WORKED_EXAMPLE in
 * backend/app/modules/demo/scenarios.py (EUR thousands), so the marketing
 * numbers are the same ones the netting engine produces in the demo.
 */

export type MemberCode = 'A' | 'B' | 'C' | 'D' | 'E' | 'F';

export interface LandingMember {
	code: MemberCode;
	city: string;
	lat: number;
	lon: number;
}

export interface Flow {
	from: MemberCode;
	to: MemberCode;
	amount: number;
}

export const MEMBERS: readonly LandingMember[] = [
	{ code: 'A', city: 'Berlin', lat: 52.52, lon: 13.4 },
	{ code: 'B', city: 'Riga', lat: 56.95, lon: 24.1 },
	{ code: 'C', city: 'Barcelona', lat: 41.39, lon: 2.17 },
	{ code: 'D', city: 'Budapest', lat: 47.5, lon: 19.04 },
	{ code: 'E', city: 'London', lat: 51.51, lon: -0.13 },
	{ code: 'F', city: 'Oslo', lat: 59.91, lon: 10.75 }
];

/** Payer → issuer, as in the backend scenario. */
export const INVOICES: readonly Flow[] = [
	{ from: 'A', to: 'B', amount: 100 },
	{ from: 'B', to: 'C', amount: 80 },
	{ from: 'C', to: 'A', amount: 60 },
	{ from: 'B', to: 'D', amount: 20 },
	{ from: 'C', to: 'F', amount: 50 },
	{ from: 'D', to: 'E', amount: 50 },
	{ from: 'E', to: 'F', amount: 60 },
	{ from: 'F', to: 'D', amount: 30 }
];

/** Net position per member: positive receives, negative pays. */
export function netPositions(flows: readonly Flow[]): Map<MemberCode, number> {
	const net = new Map<MemberCode, number>();
	for (const { from, to, amount } of flows) {
		net.set(from, (net.get(from) ?? 0) - amount);
		net.set(to, (net.get(to) ?? 0) + amount);
	}
	return net;
}

/**
 * Greedy settlement of net positions: largest payer to largest receiver until
 * every position is zero. Good enough for an illustration; the real engine
 * lives in the backend.
 */
export function settle(flows: readonly Flow[]): Flow[] {
	const positions = [...netPositions(flows)].filter(([, v]) => v !== 0);
	const payers = positions.filter(([, v]) => v < 0).map(([c, v]) => ({ c, v: -v }));
	const receivers = positions.filter(([, v]) => v > 0).map(([c, v]) => ({ c, v }));
	const out: Flow[] = [];
	while (payers.length && receivers.length) {
		payers.sort((x, y) => y.v - x.v);
		receivers.sort((x, y) => y.v - x.v);
		const p = payers[0];
		const r = receivers[0];
		const amount = Math.min(p.v, r.v);
		out.push({ from: p.c, to: r.c, amount });
		p.v -= amount;
		r.v -= amount;
		if (p.v === 0) payers.shift();
		if (r.v === 0) receivers.shift();
	}
	return out;
}

export const PAYMENTS: readonly Flow[] = settle(INVOICES);

export const total = (flows: readonly Flow[]) => flows.reduce((sum, f) => sum + f.amount, 0);

export const GROSS = total(INVOICES);
export const NET = total(PAYMENTS);
/** Share of money that no longer moves, as a whole percent. */
export const SAVED_PCT = Math.round((1 - NET / GROSS) * 100);
