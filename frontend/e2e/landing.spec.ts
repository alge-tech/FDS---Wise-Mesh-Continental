import { expect, test } from '@playwright/test';

test('landing page renders the hero and a Log in link', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
	await expect(page.getByRole('link', { name: 'Log in' }).first()).toBeVisible();
});
