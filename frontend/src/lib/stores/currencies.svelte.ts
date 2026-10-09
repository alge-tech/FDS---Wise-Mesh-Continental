import { createQuery } from '@tanstack/svelte-query';
import { currenciesQueryOptions } from '$lib/api/queries';
import type { Currency } from '$lib/api/types';

/**
 * Reactive view of `/v1/currencies`. The query is cached for the session, so every Money on a
 * page shares one request. Call during component initialisation.
 */
export function useCurrencies() {
	const query = createQuery(() => currenciesQueryOptions());
	const byCode: Readonly<Record<string, Currency>> = $derived(
		Object.fromEntries((query.data?.items ?? []).map((currency) => [currency.code, currency]))
	);

	return {
		get isPending() {
			return query.isPending;
		},
		get isError() {
			return query.isError;
		},
		get items(): Currency[] {
			return query.data?.items ?? [];
		},
		/** The served exponent, or undefined while loading or for an unknown currency. */
		exponentOf(code: string): number | undefined {
			return Object.hasOwn(byCode, code) ? byCode[code].exponent : undefined;
		}
	};
}
