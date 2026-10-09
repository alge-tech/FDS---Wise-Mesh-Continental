<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { resolve } from '$app/paths';
	import { api, type Invoice } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import Button from '$lib/components/Button.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import QueryState from '$lib/components/QueryState.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import InvoiceTable from '$lib/components/InvoiceTable.svelte';
	let { data } = $props();
	let direction = $state<'RECEIVABLE' | 'PAYABLE'>('RECEIVABLE');
	let status = $state('');
	let extra = $state<Invoice[]>([]);
	let cursor = $state<string | null>(null);
	let loading = $state(false);
	let loadError = $state('');
	const invoices = createQuery(() => ({
		queryKey: ['mesh', 'invoices', direction, status],
		queryFn: () =>
			unwrap(
				api.GET('/v1/invoices', {
					params: { query: { direction, ...(status ? { status: [status] } : {}) } }
				})
			)
	}));
	const items = $derived([...(invoices.data?.items ?? []), ...extra]);
	function changeFilters() {
		extra = [];
		cursor = null;
		loadError = '';
	}
	async function more() {
		loading = true;
		loadError = '';
		try {
			const page = await unwrap(
				api.GET('/v1/invoices', {
					params: {
						query: {
							direction,
							...(status ? { status: [status] } : {}),
							cursor: cursor ?? invoices.data?.next_cursor ?? undefined
						}
					}
				})
			);
			extra = [...extra, ...page.items];
			cursor = page.next_cursor ?? '';
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Could not load invoices.';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head><title>Invoices · Wise Mesh</title></svelte:head>
<div class="flex flex-col gap-8">
	<PageHeader
		title="Invoices"
		description="Only terms confirmed by both businesses enter the next netting window."
	/>
	<div class="flex flex-wrap items-center justify-between gap-4">
		<div class="flex gap-2" role="group" aria-label="Invoice direction">
			<Button
				variant={direction === 'RECEIVABLE' ? 'primary' : 'secondary'}
				onclick={() => {
					direction = 'RECEIVABLE';
					changeFilters();
				}}>Receivable</Button
			>
			<Button
				variant={direction === 'PAYABLE' ? 'primary' : 'secondary'}
				onclick={() => {
					direction = 'PAYABLE';
					changeFilters();
				}}>Payable</Button
			>
		</div>
		<label class="sr-only" for="invoice-status">Status</label><select
			id="invoice-status"
			bind:value={status}
			onchange={changeFilters}
			><option value="">All statuses</option
			>{#each ['UNMATCHED', 'PENDING_CONFIRMATION', 'CONFIRMED', 'DISPUTED', 'LOCKED_IN_RUN'] as s (s)}<option
					value={s}>{s.toLowerCase().replaceAll('_', ' ')}</option
				>{/each}</select
		>
		{#if data.me.role !== 'APPROVER'}<Button href={resolve('/invoices/upload')}>Add invoices</Button
			>{/if}
	</div>
	<QueryState
		pending={invoices.isPending}
		error={invoices.error}
		retry={() => invoices.refetch()}
	/>
	{#if items.length}<InvoiceTable {items} />{:else if invoices.isSuccess}<EmptyState
			title="No invoices here"
			description="Upload a CSV or create an invoice to request confirmation."
		/>{/if}
	{#if loadError}<p role="alert">{loadError}</p>{/if}
	{#if cursor === null ? invoices.data?.next_cursor : cursor}<Button
			variant="secondary"
			{loading}
			onclick={more}>Load more</Button
		>{/if}
</div>
