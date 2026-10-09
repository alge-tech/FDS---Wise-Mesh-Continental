import { expect, test, type APIRequestContext } from '@playwright/test';
import { as, PASSWORD, resetDemo } from './helpers';

/** Ops loads the worked example, every counterparty confirms, and the window closes. */
async function closeWorkedExample(request: APIRequestContext) {
	const headers = { 'X-Requested-With': 'mesh-web' };
	const post = (path: string, data?: object) =>
		request.post(path, {
			headers: { ...headers, 'Idempotency-Key': crypto.randomUUID() },
			data
		});
	expect(
		(
			await request.post('/v1/auth/login', {
				headers,
				data: { email: 'ops@wise.test', password: PASSWORD }
			})
		).ok()
	).toBeTruthy();
	expect((await post('/v1/demo/scenarios/worked_example')).ok()).toBeTruthy();
	expect((await post('/v1/demo/simulate-confirmations', { confirm_pct: 100 })).ok()).toBeTruthy();
	expect((await post('/v1/admin/windows/current/close', { reason_code: 'E2E' })).ok()).toBeTruthy();
}

test('member admin edits settings and sees the team', async ({ browser, request }) => {
	await resetDemo(request);
	const admin = await as(browser, 'admin@member-a.test');
	await admin.page.goto('/settings');
	await expect(admin.page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible();
	await expect(admin.page.getByRole('cell', { name: 'finance@member-a.test' })).toBeVisible();

	await admin.page.getByLabel('Payable limit per run').fill('45000.5');
	await admin.page.getByRole('button', { name: 'Save settings' }).click();
	await expect(admin.page.getByRole('status')).toContainText('Settings saved');
	await admin.page.reload();
	await expect(admin.page.getByLabel('Payable limit per run')).toHaveValue('45000.50');

	await admin.page.getByLabel('Maker-checker threshold').fill('12.345');
	await admin.page.getByRole('button', { name: 'Save settings' }).click();
	await expect(admin.page.getByText('Use at most 2 decimal places')).toBeVisible();
	await admin.close();
});

test('finance user withdraws an invoice and gets a recomputed statement', async ({
	browser,
	request
}) => {
	await resetDemo(request);
	await closeWorkedExample(request);

	const a = await as(browser, 'finance@member-a.test');
	await a.page.goto('/runs');
	await a.page.getByRole('link', { name: 'Review statement', exact: true }).first().click();
	await expect(a.page.getByRole('link', { name: 'WX-2026-001' })).toBeVisible();

	await a.page.getByRole('button', { name: 'Withdraw invoices' }).click();
	await a.page.getByRole('checkbox', { name: 'Withdraw WX-2026-001' }).check();
	await a.page.getByLabel('Reason').fill('PAID_OUTSIDE_MESH');
	await a.page.getByRole('button', { name: 'Withdraw 1 invoice' }).click();
	await expect(a.page).toHaveURL(/\/runs\/[0-9a-f-]+$/);

	await a.page.getByRole('link', { name: 'Review your statement' }).click();
	await expect(a.page.getByRole('heading', { name: 'Your netting statement' })).toBeVisible();
	await expect(a.page.getByRole('link', { name: 'WX-2026-003' })).toBeVisible();
	await expect(a.page.getByRole('link', { name: 'WX-2026-001' })).toHaveCount(0);
	await a.close();
});
