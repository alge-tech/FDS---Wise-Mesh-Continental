/**
 * M5 demo script: reset, upload, simulate confirmations, close the window, approve,
 * settle and see savings. It starts with a reset, so it passes run after run
 * (`bunx playwright test e2e/demo.spec.ts --repeat-each=2`).
 *
 * Worked example: 8 invoices worth €450,000 become 3 transfers worth €80,000. Member A pays
 * €40,000 plus a €78 Mesh fee and saves €234 against paying its €100,000 invoice gross.
 */
import { expect, test } from '@playwright/test';
import { as } from './helpers';

// Member A's side of the worked example. The scenario loader skips these as duplicates.
const CSV = [
	'invoice_number,issuer_tax_id,payer_tax_id,currency,amount,outstanding,issue_date,due_date',
	'WX-2026-001,LV400000002,DE811000001,EUR,100000.00,,2026-09-01,2026-10-31',
	'WX-2026-003,DE811000001,ESB0000003,EUR,60000.00,,2026-09-03,2026-10-31'
].join('\n');

test('demo script: upload to settlement and savings', async ({ browser }) => {
	test.setTimeout(180_000);

	// 1. Reset: ops wipes and re-seeds; the session survives the reset.
	const ops = await as(browser, 'ops@wise.test');
	await ops.page.getByRole('link', { name: 'Demo', exact: true }).click();
	await ops.page.getByRole('button', { name: 'Reset demo data' }).click();
	await ops.page.getByRole('button', { name: 'Delete everything and re-seed' }).click();
	await expect(ops.page.getByRole('status')).toContainText('Demo data reset.');
	await ops.page.reload();
	await expect(ops.page.getByRole('heading', { name: 'Demo controls' })).toBeVisible();

	// 2. Upload: Member A adds its two invoices from a CSV. A's browser stays open throughout.
	const a = await as(browser, 'finance@member-a.test');
	await a.page.goto('/invoices/upload');
	await a.page.getByLabel('CSV file').setInputFiles({
		name: 'member-a.csv',
		mimeType: 'text/csv',
		buffer: Buffer.from(CSV)
	});
	await a.page.getByRole('button', { name: 'Upload invoices' }).click();
	await expect(a.page.getByRole('status')).toContainText('2 accepted · 0 rejected');

	// 3. Ops loads the rest of the worked example and simulates the counterparties' replies.
	await ops.page.getByRole('button', { name: 'Load worked example' }).click();
	await expect(ops.page.getByRole('status')).toContainText('"created":6');
	await ops.page.getByRole('button', { name: 'Simulate confirmations' }).click();
	await expect(ops.page.getByRole('status')).toContainText('"confirmed":8');

	// 4. Close the window: freeze, screen, net and issue statements.
	await ops.page.getByRole('link', { name: 'Ops console', exact: true }).click();
	await expect(ops.page.getByText('8 eligible invoices', { exact: false })).toBeVisible();
	await ops.page.getByRole('button', { name: 'Close window', exact: true }).click();
	await ops.page.getByLabel('Reason for closing').fill('DEMO_CLOSE');
	await ops.page.getByRole('button', { name: 'Freeze and compute' }).click();
	await expect(ops.page.getByRole('status').first()).toContainText('Window closed.');

	// The network view shows the whole graph before and after netting.
	await ops.page.getByRole('link', { name: 'Network', exact: true }).click();
	await expect(ops.page.getByText('3 instead of 8')).toBeVisible();
	await ops.page.getByRole('button', { name: /Settlement transfers · 3/ }).click();
	await expect(
		ops.page.getByRole('img', { name: /Transfers after netting: 4 parties/ })
	).toBeVisible();

	// 5. Every member reviews its own statement and approves it.
	for (const code of ['a', 'b', 'c', 'd', 'e', 'f']) {
		const member = code === 'a' ? a : await as(browser, `finance@member-${code}.test`);
		await member.page.goto('/runs');
		await member.page.getByRole('link', { name: 'Review statement', exact: true }).first().click();
		await expect(
			member.page.getByRole('heading', { name: 'Your netting statement' })
		).toBeVisible();
		if (code === 'a') {
			await expect(
				member.page.getByText('You will pay EUR 40078.00, including the Mesh fee.', {
					exact: false
				})
			).toBeVisible();
		}
		await member.page.getByRole('button', { name: 'Approve statement', exact: true }).click();
		await expect(member.page.getByRole('status')).toContainText('Approval saved.');
		if (code !== 'a') await member.close();
	}

	// 6. Settle: holds, one commit entry, clearing back to zero.
	await ops.page.getByRole('link', { name: 'Ops console', exact: true }).click();
	await ops.page.getByRole('button', { name: 'Settle run', exact: true }).click();
	await ops.page.getByLabel('Reason for settling').fill('DEMO_SETTLE');
	await ops.page.getByRole('button', { name: 'Hold funds and commit' }).click();
	await expect(ops.page.getByText('Run settled. Clearing is back to zero.')).toBeVisible();
	await expect(ops.page.locator('[data-status="COMMITTED"]').first()).toBeVisible();
	await ops.page.getByRole('button', { name: 'Run ledger check' }).click();
	await expect(ops.page.getByText('Ledger OK', { exact: false })).toBeVisible();
	await expect(ops.page.getByText('Run clearing accounts: all zero')).toBeVisible();
	await ops.close();

	// 7. Member A sees the settlement, its new balance and its savings.
	const after = a;
	await after.page.getByRole('link', { name: 'Dashboard', exact: true }).click();
	await expect(after.page.getByText('€109,922.00')).toBeVisible();
	await after.page.goto('/runs');
	await after.page.getByRole('link', { name: /\d{4}/ }).first().click();
	await expect(after.page.getByText('Settled. Your invoices in this run are paid')).toBeVisible();
	await expect(after.page.getByRole('cell', { name: 'Paid to Mesh settlement' })).toBeVisible();
	await after.page.getByRole('link', { name: 'Savings', exact: true }).click();
	await expect(
		after.page.getByText('Saved across 1 settled run, after the Mesh fee')
	).toBeVisible();
	await expect(after.page.getByText('€234.00').first()).toBeVisible();
	await expect(after.page.getByText(/^You keep/)).toContainText('€234.00');
	// Moving the fee-share slider re-prices through /v1/estimates without saving anything.
	await after.page.getByLabel(/Mesh fee share/).fill('5000');
	await expect(after.page.getByText(/^You keep/)).toContainText('€156.00');
	await after.page.screenshot({ path: 'test-results/m5-savings.png', fullPage: true });
	await after.close();
});
