import { redirect } from '@sveltejs/kit';
import { meQueryOptions } from '$lib/api/queries';
import { queryClient } from '$lib/api/query-client';
import { safeNextPath } from '$lib/auth';
import type { PageLoad } from './$types';

// Already signed in → skip the form. If the API is unreachable, show the form anyway.
export const load: PageLoad = async ({ url }) => {
	const me = await queryClient.fetchQuery(meQueryOptions()).catch(() => null);
	if (me) redirect(307, safeNextPath(url.searchParams.get('next'), me.role));
	return {};
};
