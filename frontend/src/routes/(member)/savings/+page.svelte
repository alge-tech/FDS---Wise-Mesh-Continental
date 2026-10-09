<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { resolve } from '$app/paths';
	import { api } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import { localTime } from '$lib/dates';
	import BreakEvenSlider from '$lib/components/BreakEvenSlider.svelte';
	import Card from '$lib/components/Card.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Money from '$lib/components/Money.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import QueryState from '$lib/components/QueryState.svelte';
	import SavingsMeter from '$lib/components/SavingsMeter.svelte';
	import StatusChip from '$lib/components/StatusChip.svelte';

	let { data } = $props();

	const savings = createQuery(() => ({
		queryKey: ['mesh', 'savings'],
		queryFn: () => unwrap(api.GET('/v1/savings'))
	}));
	const latest = $derived(savings.data?.items[0] ?? null);
	// The slider starts at the price the latest statement used.
	const statement = createQuery(() => ({
		queryKey: ['mesh', 'run', latest?.run_id],
		queryFn: () =>
			unwrap(api.GET('/v1/runs/{run_id}', { params: { path: { run_id: latest!.run_id } } })),
		enabled: !!latest
	}));
	const pricing = createQuery(() => ({
		queryKey: ['mesh', 'statement', statement.data?.statement_id],
		queryFn: () =>
			unwrap(
				api.GET('/v1/statements/{statement_id}', {
					params: { path: { statement_id: statement.data!.statement_id! } }
				})
			),
		enabled: !!statement.data?.statement_id
	}));
	const price = $derived(pricing.data?.pricing);
</script>

<div class="flex flex-col gap-8">
	<PageHeader
		title="Savings"
		description="What netting saved you, per run and in total, after the Mesh fee."
	/>
	<QueryState pending={savings.isPending} error={savings.error} retry={() => savings.refetch()} />
	{#if savings.data}
		<Card class="bg-brand-pale">
			<h2 class="mb-4 text-title-group">Total savings</h2>
			<SavingsMeter totals={savings.data.totals} />
		</Card>

		<section class="flex flex-col gap-3">
			<h2 class="text-title-group">Per run</h2>
			{#if savings.data.items.length}
				<div class="overflow-x-auto rounded-card ring-1 ring-content-primary/10">
					<table class="w-full min-w-[880px] text-left text-body-default">
						<thead class="bg-background-neutral">
							<tr>
								<th>Run</th>
								<th>Status</th>
								<th class="text-right">Gross payables</th>
								<th class="text-right">Paid · received</th>
								<th class="text-right">Paying gross</th>
								<th class="text-right">Mesh fee</th>
								<th class="text-right">With Mesh</th>
								<th class="text-right">Savings</th>
							</tr>
						</thead>
						<tbody>
							{#each savings.data.items as item (item.run_id)}
								<tr class="border-t border-content-primary/10">
									<td
										><a
											class="link-default"
											href={resolve('/(member)/runs/[id]', { id: item.run_id })}
											>{item.settled_at ? localTime(item.settled_at) : 'In progress'}</a
										></td
									>
									<td><StatusChip kind="run" status={item.status} /></td>
									<td class="text-right"><Money money={item.gross_payable} /></td>
									<td class="text-right"
										><Money money={item.net_paid} /> · <Money money={item.net_received} /></td
									>
									<td class="text-right"><Money money={item.baseline} /></td>
									<td class="text-right"><Money money={item.fee} /></td>
									<td class="text-right"><Money money={item.actual} /></td>
									<td class="text-right text-body-default-bold"
										><Money
											money={item.savings}
											class="text-sentiment-positive"
										/>{#if !item.settled}
											<span class="block text-content-tertiary">projected</span>{/if}</td
									>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				<p class="text-body-default text-content-tertiary">
					Runs still in progress are projected and not counted in the total. Price version
					{latest?.price_version}.
				</p>
			{:else}
				<EmptyState
					title="No runs yet"
					description="Your savings appear after Wise closes a window with your confirmed invoices."
				/>
			{/if}
		</section>

		<BreakEvenSlider
			runId={latest?.run_id ?? null}
			currency={latest?.currency ?? data.member.settlement_currency}
			standardRateBps={price?.standard_rate_bps ?? 52}
			feeShareBps={price?.fee_share_bps ?? 2500}
		/>
	{/if}
</div>
