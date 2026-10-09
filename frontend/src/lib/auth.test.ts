import { describe, expect, it } from 'vitest';
import { homeFor, isWiseRole, roleLabel, safeNextPath } from './auth';

describe('role routing', () => {
	it('sends Wise staff to /admin and members to /dashboard', () => {
		expect(homeFor('WISE_OPS')).toBe('/admin');
		expect(homeFor('WISE_COMPLIANCE')).toBe('/admin');
		expect(homeFor('MEMBER_ADMIN')).toBe('/dashboard');
		expect(homeFor('FINANCE_USER')).toBe('/dashboard');
		expect(homeFor('APPROVER')).toBe('/dashboard');
		expect(isWiseRole('APPROVER')).toBe(false);
	});

	it('labels roles in sentence case', () => {
		expect(roleLabel('FINANCE_USER')).toBe('Finance user');
		expect(roleLabel('SOMETHING_NEW')).toBe('SOMETHING_NEW');
	});
});

describe('safeNextPath', () => {
	it('keeps a next path inside the role area', () => {
		expect(safeNextPath('/invoices?tab=payable', 'FINANCE_USER')).toBe('/invoices?tab=payable');
		expect(safeNextPath('/admin/network', 'WISE_OPS')).toBe('/admin/network');
	});

	it('refuses paths outside the role area', () => {
		expect(safeNextPath('/admin', 'FINANCE_USER')).toBe('/dashboard');
		expect(safeNextPath('/invoices', 'WISE_OPS')).toBe('/admin');
	});

	it('refuses off-site and degenerate targets', () => {
		for (const next of [
			null,
			'',
			'https://evil.test',
			'//evil.test',
			'/\\evil.test',
			'/login',
			'/'
		]) {
			expect(safeNextPath(next, 'APPROVER')).toBe('/dashboard');
		}
	});
});
