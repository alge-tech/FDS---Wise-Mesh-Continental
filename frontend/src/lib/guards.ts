import { error, redirect } from '@sveltejs/kit';
import { ApiError } from '$lib/api/client';
import { currenciesQueryOptions, meQueryOptions } from '$lib/api/queries';
import { queryClient } from '$lib/api/query-client';
import type { Me } from '$lib/api/types';

/** Turn an API failure inside a load function into a SvelteKit error page with useful text. */
export function toPageError(cause: unknown): never {
	if (cause instanceof ApiError) {
		const status = cause.status >= 400 && cause.status <= 599 ? cause.status : 503;
		error(status, { message: cause.message, code: cause.code, correlationId: cause.correlationId });
	}
	error(500, { message: 'Something went wrong while loading this page.' });
}

/**
 * Load the session for a protected area. No session → /login, remembering the current path.
 * Also warms the currencies cache so every Money on the page has its exponent.
 */
export async function requireSession(url: URL): Promise<Me> {
	let me: Me | null;
	try {
		[me] = await Promise.all([
			queryClient.fetchQuery(meQueryOptions()),
			queryClient.ensureQueryData(currenciesQueryOptions())
		]);
	} catch (cause) {
		toPageError(cause);
	}
	if (!me) {
		redirect(307, `/login?next=${encodeURIComponent(url.pathname + url.search)}`);
	}
	return me;
}

/** Page-level role check for screens only some member roles may use. */
export function requireRole(me: Me, roles: readonly string[], screen: string): void {
	if (!roles.includes(me.role)) {
		error(403, { message: `Your role cannot open ${screen}.`, code: 'FORBIDDEN' });
	}
}
