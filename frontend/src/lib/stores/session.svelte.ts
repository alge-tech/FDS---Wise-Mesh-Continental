import { createQuery } from '@tanstack/svelte-query';
import { meQueryOptions } from '$lib/api/queries';
import { homeFor, type HomePath } from '$lib/auth';

/**
 * Where the public pages should send their call to action: the role's home when a session
 * exists, otherwise the login page. Call during component initialisation.
 */
export function useSessionHome() {
	const query = createQuery(() => ({ ...meQueryOptions(), retry: false }));

	return {
		get signedIn(): boolean {
			return !!query.data;
		},
		/** The role's home, or undefined when signed out (or the API is unreachable). */
		get home(): HomePath | undefined {
			return query.data ? homeFor(query.data.role) : undefined;
		}
	};
}
