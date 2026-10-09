import { expect, test, type Page } from '@playwright/test';
import { resetDemo } from './helpers';

async function login(page: Page, email: string) {
	await page.goto('/login');
	await page.getByLabel('Email', { exact: true }).fill(email);
	await page.getByLabel('Password', { exact: true }).fill('mesh-demo-2026');
	await page.getByRole('button', { name: 'Log in', exact: true }).click();
	await expect(page).toHaveURL(email === 'ops@wise.test' ? /\/admin$/ : /\/dashboard$/);
}

test('invoice creation, confirmation, statement approval, and logo home navigation', async ({
	browser,
	request
}) => {
	// Start clean: the window must hold only this test's A/B invoice.
	await resetDemo(request);
	const context = await browser.newContext();
	const page = await context.newPage();
	const errors: string[] = [];
	page.on('pageerror', (e) => errors.push(e.message));
	await login(page, 'finance@member-a.test');
	await page.getByRole('link', { name: 'Wise Mesh, home', exact: true }).click();
	await expect(page).toHaveURL('http://localhost:3010/');
	await expect(
		page.getByRole('heading', { name: 'Pay the difference, not every invoice' })
	).toBeVisible();
	await page.goto('/invoices/upload');
	await page.getByRole('button', { name: 'Create one invoice' }).click();
	const number = `E2E-${Date.now()}`;
	await page.getByLabel('Invoice number', { exact: true }).fill(number);
	await page
		.getByLabel('Issuer tax ID or registration number', { exact: true })
		.fill('DE811000001');
	await page.getByLabel('Payer tax ID or registration number', { exact: true }).fill('LV400000002');
	await page.getByLabel('Gross amount', { exact: true }).fill('125.00');
	await page.getByRole('button', { name: 'Create invoice', exact: true }).click();
	await expect(page.getByRole('status')).toContainText('1 accepted');
	await page.getByRole('link', { name: number, exact: true }).click();
	await expect(page.getByRole('heading', { name: number, exact: true })).toBeVisible();
	const invoiceUrl = page.url();
	await context.close();
	const bContext = await browser.newContext();
	const b = await bContext.newPage();
	await login(b, 'finance@member-b.test');
	await b.goto('/confirmations');
	await b.getByRole('link', { name: number, exact: true }).click();
	await b.getByRole('button', { name: 'Confirm terms' }).click();
	await expect(b.getByText('Confirmed.', { exact: true })).toBeVisible();
	await bContext.close();
	const opsContext = await browser.newContext();
	const ops = await opsContext.newPage();
	await login(ops, 'ops@wise.test');
	await ops.getByRole('button', { name: 'Close window', exact: true }).click();
	await ops.getByLabel('Reason for closing').fill('E2E_CLOSE');
	await ops.getByRole('button', { name: 'Freeze and compute' }).click();
	await expect(ops.getByRole('status')).toContainText('Window closed.');
	await opsContext.close();
	const aContext = await browser.newContext();
	const a = await aContext.newPage();
	await login(a, 'finance@member-a.test');
	await a.goto('/runs');
	await a.getByRole('link', { name: 'Review statement', exact: true }).first().click();
	await expect(a.getByRole('heading', { name: 'Your netting statement' })).toBeVisible();
	await expect(a.getByRole('link', { name: number, exact: true })).toBeVisible();
	await expect(a.getByText('Mesh settlement', { exact: false }).first()).toBeVisible();
	await a.getByRole('button', { name: 'Approve statement', exact: true }).click();
	await expect(a.getByRole('status')).toContainText('Approval saved.');
	await a.screenshot({ path: 'test-results/m3-statement.png', fullPage: true });
	await a.setViewportSize({ width: 390, height: 844 });
	await expect(a.getByRole('heading', { name: 'Your netting statement' })).toBeVisible();
	expect(await a.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
	await a.screenshot({ path: 'test-results/m3-statement-mobile.png', fullPage: true });
	await a.goto(invoiceUrl);
	await expect(a.getByText('In netting run', { exact: true })).toBeVisible();
	const approvalContext = await browser.newContext();
	const approvalPage = await approvalContext.newPage();
	await login(approvalPage, 'finance@member-b.test');
	await approvalPage.goto('/runs');
	await approvalPage.getByRole('link', { name: 'Review statement', exact: true }).first().click();
	await approvalPage.getByRole('button', { name: 'Approve statement', exact: true }).click();
	await expect(
		approvalPage.getByText('All members have approved this run.', { exact: true })
	).toBeVisible();
	await approvalContext.close();
	expect(errors).toEqual([]);
	await aContext.close();
});
