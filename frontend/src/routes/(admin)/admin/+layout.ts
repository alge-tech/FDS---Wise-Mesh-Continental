import { redirect } from '@sveltejs/kit';
import { isWiseRole } from '$lib/auth';
import { requireSession } from '$lib/guards';
import type { LayoutLoad } from './$types';

// Wise staff only; members are sent to their dashboard.
export const load: LayoutLoad = async ({ url }) => {
	const me = await requireSession(url);
	if (!isWiseRole(me.role)) redirect(307, '/dashboard');
	return { me };
};
