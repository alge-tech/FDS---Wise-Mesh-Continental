<script lang="ts">
	import { api, refreshMesh, type Run } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import { localTime } from '$lib/dates';
	import { adminRunSummary, canAbort, canSettle } from '$lib/runs';
	import Button from '$lib/components/Button.svelte';
	import Card from '$lib/components/Card.svelte';
	import Money from '$lib/components/Money.svelte';
	import StatusChip from '$lib/components/StatusChip.svelte';

	interface Props {
		run: Run;
		role: string;
	}

	let { run, role }: Props = $props();

	let action = $state<'SETTLE' | 'ABORT' | null>(null);
	let reason = $state('');
	let busy = $state(false);
	let error = $state('');
	let message = $state('');

	const detail = $derived(run.settlement_detail);
	const money = (byCurrency: unknown) =>
		Object.entries((byCurrency ?? {}) as Record<string, number>).map(
			([currency, amount_minor]) => ({
				currency,
				amount_minor
			})
		);

	function outcome(after: Run, before: Run): string {
		if (after.status === 'COMMITTED') return 'Run settled. Clearing is back to zero.';
		if (after.status === 'ABORTED') return `Run aborted (${after.status_reason}). Holds released.`;
		if (after.status === 'FALLBACK_GROSS') return 'Recompute limit reached; invoices released.';
		if (after.current_attempt !== before.current_attempt)
			return 'Prepare excluded a member and recomputed. New statements need approval.';
		return `Run is ${after.status.toLowerCase().replaceAll('_', ' ')}.`;
	}

	async function submit() {
		busy = true;
		error = '';
		message = '';
		try {
			const body = { reason_code: reason };
			const params = { path: { run_id: run.id } };
			const after = await unwrap(
				action === 'SETTLE'
					? api.POST('/v1/admin/runs/{run_id}/settle', { params, body })
					: api.POST('/v1/admin/runs/{run_id}/abort', { params, body })
			);
			message = outcome(after, run);
			action = null;
			reason = '';
			await refreshMesh();
		} catch (e) {
			error = e instanceof Error ? e.message : 'The action failed.';
		} finally {
			busy = false;
		}
	}
</script>

<Card class="flex flex-col gap-4">
	<div class="flex flex-wrap items-center justify-between gap-3">
		<p class="text-body-large-bold">
			{localTime(run.started_at)} · Computation {run.current_attempt}
		</p>
		<StatusChip kind="run" status={run.status} />
	</div>
	<p>{adminRunSummary(run.status)}</p>

	{#if (role === 'WISE_OPS' && canSettle(run.status)) || canAbort(run.status)}
		<div class="flex flex-wrap gap-3">
			{#if role === 'WISE_OPS' && canSettle(run.status)}
				<Button
					disabled={busy}
					onclick={() => {
						action = 'SETTLE';
						reason = '';
					}}>{run.status === 'PREPARED' ? 'Resume settlement' : 'Settle run'}</Button
				>
			{/if}
			{#if canAbort(run.status)}
				<Button
					variant="secondary"
					disabled={busy}
					onclick={() => {
						action = 'ABORT';
						reason = '';
					}}>Abort run</Button
				>
			{/if}
		</div>
	{/if}
	{#if action}
		<form
			class="flex flex-col gap-4"
			onsubmit={(e) => {
				e.preventDefault();
				submit();
			}}
		>
			<p>
				{action === 'SETTLE'
					? 'Settle places a hold on each payer for its net payable plus fee, then posts one journal entry. A funding failure removes that payer and recomputes.'
					: 'Abort releases every hold and returns the invoices to the next window.'}
			</p>
			<label
				>{action === 'SETTLE' ? 'Reason for settling' : 'Reason for aborting'}<input
					bind:value={reason}
					required
				/></label
			>
			<div class="flex gap-3">
				<Button type="submit" loading={busy}
					>{action === 'SETTLE' ? 'Hold funds and commit' : 'Abort and release holds'}</Button
				><Button variant="link" onclick={() => (action = null)}>Cancel</Button>
			</div>
		</form>
	{/if}
	{#if error}<p role="alert" class="text-sentiment-negative">{error}</p>{/if}
	{#if message}<p role="status" class="text-body-default-bold">{message}</p>{/if}

	{#if detail && (detail.holds.length || detail.transfers.length)}
		<details open={run.status === 'PREPARED' || run.status === 'COMMITTED'}>
			<summary class="cursor-pointer text-body-default-bold">Settlement</summary>
			<div class="mt-4 grid gap-6 lg:grid-cols-2">
				<div class="flex flex-col gap-2">
					<h3 class="text-title-group text-content-secondary">Transfers</h3>
					<table class="w-full text-left text-body-default">
						<thead
							><tr><th>From</th><th>To</th><th class="text-right">Amount</th><th>Status</th></tr
							></thead
						>
						<tbody>
							{#each detail.transfers as t, index (index)}
								<tr class="border-t border-content-primary/10">
									<td>{t.payer}</td><td>{t.receiver}</td>
									<td class="text-right"
										><Money money={{ amount_minor: t.amount_minor, currency: t.currency }} /></td
									>
									<td>{t.status.toLowerCase()}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				<div class="flex flex-col gap-2">
					<h3 class="text-title-group text-content-secondary">Holds</h3>
					{#if detail.holds.length}
						<table class="w-full text-left text-body-default">
							<thead><tr><th>Member</th><th class="text-right">Held</th><th>Status</th></tr></thead>
							<tbody>
								{#each detail.holds as h (h.member_id + h.currency)}
									<tr class="border-t border-content-primary/10">
										<td>{h.member_name}</td>
										<td class="text-right"
											><Money money={{ amount_minor: h.amount_minor, currency: h.currency }} /></td
										>
										<td>{h.status.toLowerCase()}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					{:else}
						<p class="text-content-tertiary">No holds yet. Settle places them.</p>
					{/if}
					{#if detail.clearing.length}
						<p>
							Clearing:
							{#each detail.clearing as c, index (c.currency)}{index ? ' · ' : ''}<Money
									money={{ amount_minor: c.balance_minor, currency: c.currency }}
								/>{/each}
							{detail.clearing.every((c) => c.balance_minor === 0) ? '(zero)' : '(not zero)'}
						</p>
					{/if}
					{#if detail.commit_entry_seq}
						<p class="text-content-tertiary">
							Committed in journal entry #{detail.commit_entry_seq}
						</p>
					{/if}
				</div>
			</div>
			{#if detail.jobs.length}
				<h3 class="mt-5 mb-2 text-title-group text-content-secondary">Settlement jobs</h3>
				<ol class="flex flex-col gap-1 text-body-default">
					{#each detail.jobs.filter((j) => !j.member_id) as j, index (index)}
						<li>
							{j.step.toLowerCase()} · {j.status.toLowerCase()} · attempt {j.attempts}{j.last_error
								? ` · ${j.last_error}`
								: ''}{j.result?.outcome ? ` · ${String(j.result.outcome).toLowerCase()}` : ''}
						</li>
					{/each}
				</ol>
			{/if}
		</details>
	{/if}

	{#each run.computations as c, index (index)}{@const metrics = c.metrics as Record<
			string,
			unknown
		>}
		<details>
			<summary class="cursor-pointer"
				>Attempt {String(c.attempt)} · {String(metrics.invoice_count)} invoices · {String(
					metrics.transfer_count
				)} transfers</summary
			>
			<dl class="mt-3 grid gap-3 sm:grid-cols-2">
				<div>
					<dt class="text-content-tertiary">Gross invoice value</dt>
					<dd>
						{#each money(metrics.gross_minor) as m (m.currency)}<Money money={m} /><br />{/each}
					</dd>
				</div>
				<div>
					<dt class="text-content-tertiary">Moved after netting</dt>
					<dd>
						{#each money(metrics.net_minor) as m (m.currency)}<Money money={m} /><br />{/each}
					</dd>
				</div>
				<div>
					<dt class="text-content-tertiary">Trigger</dt>
					<dd>{String(c.trigger).toLowerCase().replaceAll('_', ' ')}</dd>
				</div>
				<div>
					<dt class="text-content-tertiary">Excluded members</dt>
					<dd>{(c.excluded_members as string[]).length}</dd>
				</div>
			</dl>
			<p class="mt-3 break-all text-content-tertiary">Input: {String(c.input_hash)}</p>
			<p class="break-all text-content-tertiary">Result: {String(c.result_hash)}</p>
		</details>
	{/each}
	<details>
		<summary class="cursor-pointer">Run activity</summary>
		<ol class="mt-3 flex flex-col gap-2">
			{#each run.timeline as e, index (index)}<li>
					{String(e.action).replaceAll('_', ' ')} · {String(e.reason ?? '')} · {localTime(
						String(e.created_at)
					)}
				</li>{/each}
		</ol>
	</details>
</Card>
