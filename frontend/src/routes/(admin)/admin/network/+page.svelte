<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { api, activeRun } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import { localTime } from '$lib/dates';
	import Card from '$lib/components/Card.svelte';
	import Money from '$lib/components/Money.svelte';
	import NetworkGraph from '$lib/components/NetworkGraph.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import QueryState from '$lib/components/QueryState.svelte';
	import StatusChip from '$lib/components/StatusChip.svelte';

	let view = $state<'INVOICES' | 'TRANSFERS'>('INVOICES');
	let runId = $state<string>('');

	const network = createQuery(() => ({
		queryKey: ['mesh', 'admin-network', runId],
		queryFn: () =>
			unwrap(api.GET('/v1/admin/network', { params: { query: runId ? { run_id: runId } : {} } })),
		refetchInterval: (q) => (activeRun(q.state.data?.run_status ?? undefined) ? 5000 : false)
	}));

	const graph = $derived(network.data);
	const edges = $derived(
		graph ? (view === 'INVOICES' ? graph.invoice_edges : graph.transfer_edges) : []
	);
	const names = $derived(Object.fromEntries((graph?.nodes ?? []).map((n) => [n.id, n.label])));
	const used = $derived(new Set(edges.flatMap((e) => [e.source, e.target])));
	const nodes = $derived((graph?.nodes ?? []).filter((n) => used.has(n.id)));
	const totals = (byCurrency: Record<string, number>) =>
		Object.entries(byCurrency).map(([currency, amount_minor]) => ({ currency, amount_minor }));
</script>

<div class="flex flex-col gap-8">
	<PageHeader
		title="Network"
		description="The whole invoice graph before netting, and the transfers that settle it."
	/>
	<QueryState pending={network.isPending} error={network.error} retry={() => network.refetch()} />
	{#if graph}
		<Card class="flex flex-col gap-5">
			<div class="flex flex-wrap items-end justify-between gap-4">
				<div class="flex flex-col items-start gap-2">
					<p class="text-body-large-bold">
						{#if graph.source === 'WINDOW'}
							Current window · eligible invoices only, nothing netted yet
						{:else}
							Run of {localTime(graph.runs.find((r) => r.id === graph.run_id)?.started_at ?? '')} · computation
							{graph.attempt}
						{/if}
					</p>
					{#if graph.run_status}<StatusChip kind="run" status={graph.run_status} />{/if}
				</div>
				{#if graph.runs.length}
					<label
						>Run<select bind:value={runId}>
							<option value="">Latest run</option>
							{#each graph.runs as r (r.id)}
								<option value={r.id}>{localTime(r.started_at)} · {r.status.toLowerCase()}</option>
							{/each}
						</select></label
					>
				{/if}
			</div>
			<div role="group" aria-label="Graph view" class="flex flex-wrap gap-3">
				<button
					type="button"
					aria-pressed={view === 'INVOICES'}
					class={[
						'h-10 rounded-pill px-5 text-body-large-bold',
						view === 'INVOICES'
							? 'bg-brand-primary text-brand-forest'
							: 'border border-content-primary/15'
					]}
					onclick={() => (view = 'INVOICES')}
					>Gross invoices · {graph.invoice_edges.reduce((n, e) => n + e.invoice_count, 0)}</button
				>
				<button
					type="button"
					aria-pressed={view === 'TRANSFERS'}
					disabled={graph.source === 'WINDOW'}
					class={[
						'h-10 rounded-pill px-5 text-body-large-bold disabled:cursor-not-allowed disabled:opacity-50',
						view === 'TRANSFERS'
							? 'bg-brand-primary text-brand-forest'
							: 'border border-content-primary/15'
					]}
					onclick={() => (view = 'TRANSFERS')}
					>Settlement transfers · {graph.transfer_edges.length}</button
				>
			</div>
			<dl class="grid gap-5 sm:grid-cols-3">
				<div>
					<dt class="text-content-tertiary">Gross invoice value</dt>
					<dd class="text-body-large-bold">
						{#each totals(graph.gross_minor) as m (m.currency)}<Money money={m} /><br
							/>{:else}—{/each}
					</dd>
				</div>
				<div>
					<dt class="text-content-tertiary">Moved after netting</dt>
					<dd class="text-body-large-bold">
						{#each totals(graph.net_minor) as m (m.currency)}<Money money={m} /><br
							/>{:else}—{/each}
					</dd>
				</div>
				<div>
					<dt class="text-content-tertiary">Payments</dt>
					<dd class="text-body-large-bold">
						{graph.transfer_edges.length} instead of {graph.invoice_edges.reduce(
							(n, e) => n + e.invoice_count,
							0
						)}
					</dd>
				</div>
			</dl>
		</Card>

		{#if edges.length}
			<NetworkGraph
				{nodes}
				{edges}
				label={view === 'INVOICES' ? 'Gross invoices before netting' : 'Transfers after netting'}
				alternative="The table below lists every flow."
			/>
			<section class="flex flex-col gap-3">
				<h2 class="text-title-group">
					{view === 'INVOICES' ? 'Invoice flows (payer to receiver)' : 'Settlement transfers'}
				</h2>
				<div class="overflow-x-auto rounded-card ring-1 ring-content-primary/10">
					<table class="w-full min-w-[560px] text-left text-body-default">
						<thead class="bg-background-neutral"
							><tr
								><th>Payer</th><th>Receiver</th><th>Kind</th><th class="text-right">Amount</th></tr
							></thead
						>
						<tbody>
							{#each edges as e (e.id)}
								<tr class="border-t border-content-primary/10">
									<td>{names[e.source]}</td><td>{names[e.target]}</td>
									<td
										>{e.kind === 'INVOICE'
											? `${e.invoice_count} invoice${e.invoice_count === 1 ? '' : 's'}`
											: e.kind === 'FX_LEG'
												? 'Currency conversion'
												: 'Settlement'}</td
									>
									<td class="text-right"
										><Money money={{ amount_minor: e.amount_minor, currency: e.currency }} /></td
									>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</section>
		{:else}
			<p class="rounded-card bg-background-neutral p-6">
				{view === 'INVOICES'
					? 'No confirmed invoices yet. Load a scenario from Demo controls.'
					: 'This computation needs no transfers: every invoice was netted.'}
			</p>
		{/if}
	{/if}
</div>
