import { goto } from '$app/navigation';
import { resolve } from '$app/paths';
import { MutationCache, QueryCache, QueryClient } from '@tanstack/svelte-query';
import { ApiError } from './client';

const PUBLIC_PATHS = new Set(['/', '/login']);

/** A session that expired mid-use sends the user back to log in, keeping where they were. */
function handleUnauthenticated(error: unknown): void {
	if (!(error instanceof ApiError) || error.status !== 401) return;
	if (error.code === 'INVALID_CREDENTIALS') return;
	const { pathname, search } = window.location;
	if (PUBLIC_PATHS.has(pathname)) return;
	queryClient.clear();
	const next = encodeURIComponent(pathname + search);
	void goto(resolve(`/login?next=${next}`), { replaceState: true });
}

function shouldRetry(failureCount: number, error: unknown): boolean {
	// Client errors are answers, not glitches: never retry 4xx.
	if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
	return failureCount < 2;
}

/**
 * One QueryClient for the whole SPA (SSR is off, so a module singleton never leaks between
 * users). Route guards use it directly in `load`; components get it from QueryClientProvider.
 */
export const queryClient = new QueryClient({
	queryCache: new QueryCache({ onError: handleUnauthenticated }),
	mutationCache: new MutationCache({ onError: handleUnauthenticated }),
	defaultOptions: {
		queries: {
			staleTime: 30_000,
			refetchOnWindowFocus: false,
			retry: shouldRetry
		},
		mutations: { retry: false }
	}
});
