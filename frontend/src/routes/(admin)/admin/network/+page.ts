import { requireRole } from '$lib/guards';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ parent }) => {
	const { me } = await parent();
	requireRole(me, ['WISE_OPS'], 'the network graph');
	return {};
};
