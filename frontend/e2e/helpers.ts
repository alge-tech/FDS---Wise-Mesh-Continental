import { expect, type APIRequestContext, type Browser, type Page } from '@playwright/test';

export const PASSWORD = 'mesh-demo-2026';

export async function login(page: Page, email: string) {
	await page.goto('/login');
	await page.getByLabel('Email', { exact: true }).fill(email);
	await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
	await page.getByRole('button', { name: 'Log in', exact: true }).click();
	await expect(page).toHaveURL(email.endsWith('@wise.test') ? /\/admin$/ : /\/dashboard$/);
}

/** A fresh browser context logged in as one persona, failing the test on any page error. */
export async function as(browser: Browser, email: string) {
	const context = await browser.newContext();
	const page = await context.newPage();
	const errors: string[] = [];
	page.on('pageerror', (e) => errors.push(e.message));
	await login(page, email);
	return {
		page,
		async close() {
			expect(errors).toEqual([]);
			await context.close();
		}
	};
}

/** Wipe and re-seed through the API (for specs that only need a clean starting point). */
export async function resetDemo(request: APIRequestContext) {
	const headers = { 'X-Requested-With': 'mesh-web' };
	const login = await request.post('/v1/auth/login', {
		headers,
		data: { email: 'ops@wise.test', password: PASSWORD }
	});
	expect(login.ok()).toBeTruthy();
	const reset = await request.post('/v1/demo/reset', {
		headers: { ...headers, 'Idempotency-Key': crypto.randomUUID() }
	});
	expect(reset.ok()).toBeTruthy();
}
