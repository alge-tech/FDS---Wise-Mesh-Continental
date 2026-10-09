/** Role helpers shared by the route guards, the login page and the app shell. */
import type { PathnameWithSearchOrHash } from '$app/types';

export const ROLES = [
	'MEMBER_ADMIN',
	'FINANCE_USER',
	'APPROVER',
	'WISE_OPS',
	'WISE_COMPLIANCE'
] as const;
export type Role = (typeof ROLES)[number];

export const WISE_ROLES: readonly Role[] = ['WISE_OPS', 'WISE_COMPLIANCE'];
export const MEMBER_ROLES: readonly Role[] = ['MEMBER_ADMIN', 'FINANCE_USER', 'APPROVER'];

export const roleLabels: Record<Role, string> = {
	MEMBER_ADMIN: 'Member admin',
	FINANCE_USER: 'Finance user',
	APPROVER: 'Approver',
	WISE_OPS: 'Wise ops',
	WISE_COMPLIANCE: 'Wise compliance'
};

export function isWiseRole(role: string): boolean {
	return (WISE_ROLES as readonly string[]).includes(role);
}

export function roleLabel(role: string): string {
	return (roleLabels as Record<string, string>)[role] ?? role;
}

export type HomePath = '/admin' | '/dashboard';

/** Where a role lands after logging in. */
export function homeFor(role: string): HomePath {
	return isWiseRole(role) ? '/admin' : '/dashboard';
}

/**
 * Validate a `?next=` redirect target: same-origin paths only, and only into the area the role
 * may use. Anything else falls back to the role's home.
 */
export function safeNextPath(
	next: string | null | undefined,
	role: string
): PathnameWithSearchOrHash {
	const home = homeFor(role);
	if (!next || !next.startsWith('/') || next.startsWith('//') || next.includes('\\')) return home;
	if (next === '/login' || next.startsWith('/login?') || next === '/') return home;
	const isAdminPath = next === '/admin' || next.startsWith('/admin/') || next.startsWith('/admin?');
	// Validated above: a same-origin path inside the role's area.
	return isAdminPath === isWiseRole(role) ? (next as PathnameWithSearchOrHash) : home;
}
