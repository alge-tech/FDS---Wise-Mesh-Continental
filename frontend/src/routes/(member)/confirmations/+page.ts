import { requireRole } from '$lib/guards';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ parent }) => {
	const { me } = await parent();
	requireRole(me, ['FINANCE_USER', 'MEMBER_ADMIN'], 'Confirmations');
	return {};
};
