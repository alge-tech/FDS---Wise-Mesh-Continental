<script lang="ts">
	import { localTime } from '$lib/dates';
	import { createQuery } from '@tanstack/svelte-query';
	import { page } from '$app/state';
	import { api } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import QueryState from '$lib/components/QueryState.svelte';
	import Card from '$lib/components/Card.svelte';
	import Money from '$lib/components/Money.svelte';
	import StatusChip from '$lib/components/StatusChip.svelte';
	import InvoiceDecision from '$lib/components/InvoiceDecision.svelte';
	let { data } = $props();
	const invoice = createQuery(() => ({
		queryKey: ['mesh', 'invoice', page.params.id],
		queryFn: () =>
			unwrap(
				api.GET('/v1/invoices/{invoice_id}', { params: { path: { invoice_id: page.params.id! } } })
			)
	}));
</script>

<svelte:head><title>Invoice · Wise Mesh</title></svelte:head>
<div class="flex flex-col gap-8">
	<QueryState pending={invoice.isPending} error={invoice.error} retry={() => invoice.refetch()} />
	{#if invoice.data}{@const i = invoice.data}<PageHeader
			title={i.invoice_number}
			description={`${i.counterparty} · Version ${i.current_version}`}
		/>
		<Card class="flex flex-col gap-6"
			><div class="flex flex-wrap items-center justify-between gap-5">
				<div>
					<StatusChip kind="invoice" status={i.status} />
					<p class="mt-3">
						{i.direction === 'PAYABLE' ? 'You pay' : 'You receive'} · Due {i.due_date}
					</p>
				</div>
				<span class="text-amount"
					><Money money={{ amount_minor: i.outstanding_minor, currency: i.currency }} /></span
				>
			</div>
			<InvoiceDecision invoice={i} writable={data.me.role !== 'APPROVER'} /></Card
		>
		<section class="flex flex-col gap-3">
			<h2 class="text-title-group">Confirmations</h2>
			{#each i.confirmations as c, index (index)}<p>
					Version {String(c.version)} · {String(c.decision).toLowerCase()} · {String(
						c.method
					).toLowerCase()}{c.reason_code ? ` · ${c.reason_code}` : ''}
				</p>{/each}
		</section>
		<section class="flex flex-col gap-3">
			<h2 class="text-title-group">Version history</h2>
			{#each i.versions as v, index (index)}<Card
					><p class="text-body-large-bold">
						Version {String(v.version)} · {String(v.change_type).toLowerCase()}
					</p>
					<dl class="mt-4 grid gap-2 sm:grid-cols-2">
						{#each Object.entries(v.changed_fields as Record<string, unknown>) as [key, value] (key)}<div
							>
								<dt class="text-content-tertiary">{key.replaceAll('_', ' ')}</dt>
								<dd>{String(value)}</dd>
							</div>{/each}
					</dl></Card
				>{/each}
		</section>
		{#if i.exclusions.length}<section>
				<h2 class="text-title-group">Window exclusions</h2>
				{#each i.exclusions as e, index (index)}<p>
						{String(e.reason).toLowerCase().replaceAll('_', ' ')}
					</p>{/each}
			</section>{/if}
		{#if i.outcomes.length}<section>
				<h2 class="text-title-group">Settlement outcomes</h2>
				{#each i.outcomes as o, index (index)}<p>
						{String(o.outcome).toLowerCase().replaceAll('_', ' ')}
					</p>{/each}
			</section>{/if}
		<section class="flex flex-col gap-3">
			<h2 class="text-title-group">Activity</h2>
			{#each i.audit as e, index (index)}<p>
					{String(e.action).replaceAll('.', ' ').replaceAll('_', ' ')}
					<span class="text-content-tertiary">{localTime(String(e.created_at))}</span>
				</p>{/each}
		</section>
	{/if}
</div>
