<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { resolve } from '$app/paths';
	import { api } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import Card from '$lib/components/Card.svelte';
	import Money from '$lib/components/Money.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import QueryState from '$lib/components/QueryState.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import InvoiceDecision from '$lib/components/InvoiceDecision.svelte';
	const inbox = createQuery(() => ({
		queryKey: ['mesh', 'confirmations'],
		queryFn: () => unwrap(api.GET('/v1/confirmations'))
	}));
</script>

<svelte:head><title>Confirmations · Wise Mesh</title></svelte:head>
<div class="flex flex-col gap-8">
	<PageHeader
		title="Confirm invoice terms"
		description="Check the amount and due date. Your response applies only to this version."
	/>
	<QueryState pending={inbox.isPending} error={inbox.error} retry={() => inbox.refetch()} />
	{#each inbox.data?.items ?? [] as invoice (invoice.id)}<Card class="flex flex-col gap-5">
			<div class="flex flex-wrap justify-between gap-4">
				<div>
					<a class="link-large" href={resolve('/(member)/invoices/[id]', { id: invoice.id })}
						>{invoice.invoice_number}</a
					>
					<p>{invoice.counterparty}</p>
					<p class="text-content-tertiary">
						{invoice.direction === 'PAYABLE' ? 'You pay' : 'You receive'} · Due {invoice.due_date} · Version
						{invoice.current_version}
					</p>
				</div>
				<span class="text-amount"
					><Money
						money={{ amount_minor: invoice.outstanding_minor, currency: invoice.currency }}
					/></span
				>
			</div>
			<InvoiceDecision {invoice} />
		</Card>{/each}
	{#if inbox.isSuccess && !inbox.data.items.length}<EmptyState
			title="All caught up"
			description="Invoices that need your confirmation will appear here."
		/>{/if}
</div>
