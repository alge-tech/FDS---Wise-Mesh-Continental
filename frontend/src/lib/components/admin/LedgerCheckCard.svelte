<script lang="ts">
	import { api, type LedgerCheck } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import { localTime } from '$lib/dates';
	import Button from '$lib/components/Button.svelte';
	import Card from '$lib/components/Card.svelte';
	import Money from '$lib/components/Money.svelte';

	let report = $state<LedgerCheck | null>(null);
	let busy = $state(false);
	let error = $state('');

	async function check() {
		busy = true;
		error = '';
		try {
			report = await unwrap(api.GET('/v1/admin/ledger/check'));
		} catch (e) {
			error = e instanceof Error ? e.message : 'The ledger check failed.';
		} finally {
			busy = false;
		}
	}
</script>

<Card class="flex flex-col gap-4">
	<h2 class="text-title-group">Ledger check</h2>
	<p>
		Walks the journal hash chain, checks every entry balances per currency, and that every run's
		clearing account is zero.
	</p>
	<Button class="self-start" variant="secondary" loading={busy} onclick={check}
		>Run ledger check</Button
	>
	{#if error}<p role="alert" class="text-sentiment-negative">{error}</p>{/if}
	{#if report}
		<div
			role="status"
			class={['rounded-card p-5', report.ok ? 'bg-brand-pale' : 'bg-background-neutral']}
		>
			<p class="text-body-large-bold">
				{report.ok ? 'Ledger OK' : 'Ledger problem found'} · {report.entries} journal entries
			</p>
			<ul class="mt-2 flex flex-col gap-1">
				<li>
					Hash chain: {report.chain_ok
						? 'intact'
						: `broken at entry #${report.first_break_seq ?? '?'}`}
				</li>
				<li>
					Entries balanced: {report.unbalanced_entries.length
						? `no (#${report.unbalanced_entries.join(', #')})`
						: 'yes'}
				</li>
				<li>Run clearing accounts: {report.clearing_ok ? 'all zero' : 'not zero'}</li>
				<li>Active holds: {report.active_holds}</li>
			</ul>
			{#each report.breaks as b (b.run_id + b.account_type + b.currency)}
				<p class="text-sentiment-negative">
					{b.account_type.toLowerCase()} of run {b.run_id.slice(0, 8)}:
					<Money money={{ amount_minor: b.balance_minor, currency: b.currency }} />
				</p>
			{/each}
			<p class="mt-2 text-content-tertiary">Checked {localTime(report.checked_at)}</p>
		</div>
	{/if}
</Card>
