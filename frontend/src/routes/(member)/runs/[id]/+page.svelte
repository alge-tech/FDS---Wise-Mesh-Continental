<script lang="ts">
	import { localTime } from '$lib/dates';
	import { createQuery } from '@tanstack/svelte-query';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { api, activeRun } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import { runSummary } from '$lib/runs';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import QueryState from '$lib/components/QueryState.svelte';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import StatusChip from '$lib/components/StatusChip.svelte';
	import Money from '$lib/components/Money.svelte';

	const run = createQuery(() => ({
		queryKey: ['mesh', 'run', page.params.id],
		queryFn: () =>
			unwrap(api.GET('/v1/runs/{run_id}', { params: { path: { run_id: page.params.id! } } })),
		refetchInterval: (q) => (activeRun(q.state.data?.status) ? 5000 : false)
	}));

	const settlementLabel: Record<string, string> = {
		PENDING: 'Waiting for approvals',
		FUNDS_HELD: 'Funds held',
		SETTLED: 'Settled',
		CANCELLED: 'Cancelled'
	};
</script>

<svelte:head><title>Run detail · Wise Mesh</title></svelte:head>
<div class="flex flex-col gap-8">
	<QueryState pending={run.isPending} error={run.error} retry={() => run.refetch()} />
	{#if run.data}{@const r = run.data}{@const s = r.settlement}<PageHeader
			title="Netting run"
			description={`Window closed ${localTime(r.started_at)} · Computation ${r.current_attempt}`}
		/>
		<Card class="flex flex-col gap-5 bg-brand-pale">
			<div class="flex flex-wrap items-center gap-3">
				<StatusChip kind="run" status={r.status} />
				{#if r.finished_at}<span class="text-content-tertiary"
						>Finished {localTime(r.finished_at)}</span
					>{/if}
			</div>
			<p class="text-body-large-bold">
				{runSummary({
					status: r.status,
					hasStatement: !!r.statement_id,
					approved: (r.approvals ?? []).some((a) => a.decision === 'APPROVED')
				})}
			</p>
			{#if s}
				<div class="flex flex-col gap-1">
					<span class="text-amount"><Money money={s.amount} /></span>
					<span>
						{s.instruction === 'DEBIT'
							? 'You pay'
							: s.instruction === 'CREDIT'
								? 'You receive'
								: 'No payment'}
						{#if s.instruction !== 'NONE'}· counterparty {s.counterparty}{/if} · reference {s.reference}
					</span>
				</div>
			{/if}
			{#if r.statement_id}<Button
					class="self-start"
					href={resolve('/(member)/statements/[id]', { id: r.statement_id })}
					variant={r.status === 'AWAITING_APPROVAL' ? 'primary' : 'secondary'}
					>{r.status === 'AWAITING_APPROVAL'
						? 'Review your statement'
						: 'View your statement'}</Button
				>{/if}
		</Card>

		{#if s}
			<section class="flex flex-col gap-4">
				<h2 class="text-title-group">Settlement</h2>
				<Card class="flex flex-col gap-5">
					<dl class="grid gap-5 sm:grid-cols-4">
						<div>
							<dt class="text-content-tertiary">Status</dt>
							<dd class="text-body-large-bold">{settlementLabel[s.status] ?? s.status}</dd>
						</div>
						<div>
							<dt class="text-content-tertiary">Held for settlement</dt>
							<dd class="text-body-large-bold">
								{#if s.held}<Money money={s.held} />{:else}Nothing held{/if}
							</dd>
						</div>
						<div>
							<dt class="text-content-tertiary">Invoices settled by netting</dt>
							<dd class="text-body-large-bold">{s.settled_by_netting}</dd>
						</div>
						<div>
							<dt class="text-content-tertiary">Invoices settled by transfer</dt>
							<dd class="text-body-large-bold">{s.settled_by_transfer}</dd>
						</div>
					</dl>
					{#if s.carried}<p>
							Below the minimum transfer and carried to the next window: <Money
								signed
								money={s.carried}
							/>
						</p>{/if}
					{#if s.ledger.length}
						<div class="overflow-x-auto">
							<table class="w-full min-w-[560px] text-left text-body-default">
								<caption class="sr-only">Your ledger lines for this run</caption>
								<thead
									><tr
										><th>Date</th><th>Movement</th><th>Account</th><th>Counterparty</th><th
											class="text-right">Amount</th
										></tr
									></thead
								>
								<tbody>
									{#each s.ledger as line, index (index)}
										<tr class="border-t border-content-primary/10">
											<td>{localTime(line.created_at)}</td>
											<td>{line.description}</td>
											<td
												>{line.account === 'BALANCE'
													? 'Balance'
													: line.account === 'HELD'
														? 'Held'
														: 'Carried'}</td
											>
											<td>{line.counterparty}</td>
											<td class="text-right"><Money signed money={line.amount} /></td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					{:else}
						<p class="text-content-tertiary">
							No money has moved yet. Ledger lines appear when Wise holds funds and settles.
						</p>
					{/if}
				</Card>
			</section>
		{/if}

		<section>
			<h2 class="mb-5 text-title-group">Run timeline</h2>
			<ol class="flex flex-col gap-4 border-l-2 border-brand-primary pl-6">
				{#each r.timeline as event, index (index)}<li>
						<p class="text-body-large-bold">
							{String(event.action).replace('run.', '').replaceAll('_', ' ')}
						</p>
						<p class="text-content-tertiary">
							{localTime(String(event.created_at))}
						</p>
					</li>{/each}
			</ol>
		</section>
	{/if}
</div>
