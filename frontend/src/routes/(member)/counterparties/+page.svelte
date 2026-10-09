<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { api } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import QueryState from '$lib/components/QueryState.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import StatusChip from '$lib/components/StatusChip.svelte';
	import NetworkGraph from '$lib/components/NetworkGraph.svelte';
	const parties = createQuery(() => ({
		queryKey: ['mesh', 'counterparties'],
		queryFn: () => unwrap(api.GET('/v1/counterparties'))
	}));
	const network = createQuery(() => ({
		queryKey: ['mesh', 'network', 'me'],
		queryFn: () => unwrap(api.GET('/v1/network/me'))
	}));
	let settled = $state(false);
	const edges = $derived(
		network.data ? (settled ? network.data.transfer_edges : network.data.invoice_edges) : []
	);
	const used = $derived(new Set(edges.flatMap((e) => [e.source, e.target])));
</script>

<svelte:head><title>Counterparties · Wise Mesh</title></svelte:head>
<div class="flex flex-col gap-8">
	<PageHeader
		title="Counterparties"
		description="Businesses connected through your own invoices. Matched businesses can confirm and net with you."
	/>
	<QueryState pending={parties.isPending} error={parties.error} retry={() => parties.refetch()} />
	{#if parties.data?.items.length}<div
			class="overflow-x-auto rounded-card ring-1 ring-content-primary/10"
		>
			<table class="w-full min-w-[640px] text-left text-body-default">
				<thead class="bg-background-neutral"
					><tr><th>Business</th><th>Identity</th><th>Match</th><th>Invoices</th></tr></thead
				><tbody
					>{#each parties.data.items as p (p.identity)}<tr
							class="border-t border-content-primary/10"
							><td>{p.name}</td><td>{p.identity}</td><td
								><StatusChip kind="invoice" status={p.status} /></td
							><td>{p.invoice_count}</td></tr
						>{/each}</tbody
				>
			</table>
		</div>{:else if parties.isSuccess}<EmptyState
			title="No counterparties yet"
			description="Add an invoice to match its counterparty by tax ID or registration number."
		/>{/if}
	{#if network.data && network.data.invoice_edges.length}
		<section class="flex flex-col gap-4">
			<div class="flex flex-wrap items-center justify-between gap-3">
				<h2 class="text-title-group">Your network</h2>
				<div role="group" aria-label="Network view" class="flex gap-2">
					<button
						type="button"
						aria-pressed={!settled}
						class={[
							'h-8 rounded-pill px-4 text-body-default-bold',
							!settled ? 'bg-brand-primary text-brand-forest' : 'border border-content-primary/15'
						]}
						onclick={() => (settled = false)}>Your invoices</button
					>
					<button
						type="button"
						aria-pressed={settled}
						disabled={!network.data.transfer_edges.length}
						class={[
							'h-8 rounded-pill px-4 text-body-default-bold disabled:opacity-50',
							settled ? 'bg-brand-primary text-brand-forest' : 'border border-content-primary/15'
						]}
						onclick={() => (settled = true)}>Your settlement</button
					>
				</div>
			</div>
			<p class="text-body-default text-content-secondary">
				{settled
					? 'After netting you settle one amount with Mesh settlement; other members stay private.'
					: 'Arrows point from the business that pays to the business that is paid.'}
			</p>
			<NetworkGraph
				nodes={network.data.nodes.filter((n) => used.has(n.id))}
				{edges}
				height={360}
				label={settled ? 'Your settlement with Mesh settlement' : 'Your invoices by counterparty'}
				alternative={settled
					? 'Your run page lists the amount.'
					: 'The table above lists each counterparty.'}
			/>
		</section>
	{/if}
</div>
