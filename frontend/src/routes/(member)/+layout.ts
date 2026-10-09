import { error, redirect } from '@sveltejs/kit';
import { isWiseRole } from '$lib/auth';
import { requireSession } from '$lib/guards';
import type { LayoutLoad } from './$types';

// Member area: a session is required; Wise staff belong in /admin.
export const load: LayoutLoad = async ({ url }) => {
	const me = await requireSession(url);
	if (isWiseRole(me.role)) redirect(307, '/admin');
	if (!me.member) {
		error(403, { message: 'This account is not linked to a Mesh member.', code: 'FORBIDDEN' });
	}
	return { me, member: me.member };
};
