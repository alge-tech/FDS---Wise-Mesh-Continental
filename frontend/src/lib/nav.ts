import type { Me } from '$lib/api/types';

export interface NavItem {
	href:
		| '/dashboard'
		| '/invoices'
		| '/confirmations'
		| '/counterparties'
		| '/runs'
		| '/savings'
		| '/settings'
		| '/admin'
		| '/admin/network'
		| '/admin/demo';
	label: string;
	/** Roles that see this item; omitted means every role in the area. */
	roles?: readonly Me['role'][];
	/** Only shown when the API runs in demo mode. */
	demoOnly?: boolean;
	/** Active only on an exact path match (for area roots such as /admin). */
	exact?: boolean;
}

export const memberNav: readonly NavItem[] = [
	{ href: '/dashboard', label: 'Dashboard' },
	{ href: '/invoices', label: 'Invoices' },
	{ href: '/confirmations', label: 'Confirmations', roles: ['MEMBER_ADMIN', 'FINANCE_USER'] },
	{ href: '/counterparties', label: 'Counterparties' },
	{ href: '/runs', label: 'Runs' },
	{ href: '/savings', label: 'Savings' },
	{ href: '/settings', label: 'Settings', roles: ['MEMBER_ADMIN'] }
];

export const adminNav: readonly NavItem[] = [
	{ href: '/admin', label: 'Ops console', exact: true },
	{ href: '/admin/network', label: 'Network', roles: ['WISE_OPS'] },
	{ href: '/admin/demo', label: 'Demo', roles: ['WISE_OPS'], demoOnly: true }
];

export function visibleNav(items: readonly NavItem[], me: Me): NavItem[] {
	return items.filter(
		(item) => (!item.roles || item.roles.includes(me.role)) && (!item.demoOnly || me.demo_mode)
	);
}

export function isActive(item: NavItem, pathname: string): boolean {
	if (item.exact) return pathname === item.href;
	return pathname === item.href || pathname.startsWith(`${item.href}/`);
}
