import { error } from '@sveltejs/kit';
import { requireRole } from '$lib/guards';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ parent }) => {
	const { me } = await parent();
	requireRole(me, ['WISE_OPS'], 'demo controls');
	if (!me.demo_mode) error(404, { message: 'Demo mode is off.', code: 'DEMO_MODE_OFF' });
	return {};
};
