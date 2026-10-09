<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import CircleAlert from '@lucide/svelte/icons/circle-alert';
	import { api } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import { resolve } from '$app/paths';
	import { memberQueryOptions } from '$lib/api/queries';
	import Button from '$lib/components/Button.svelte';
	import Card from '$lib/components/Card.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Money from '$lib/components/Money.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import SavingsMeter from '$lib/components/SavingsMeter.svelte';
	import Section from '$lib/components/Section.svelte';
	import { humaniseStatus } from '$lib/status';

	let { data } = $props();

	const member = createQuery(() => memberQueryOptions());
	const window = createQuery(() => ({
		queryKey: ['mesh', 'window'],
		queryFn: () => unwrap(api.GET('/v1/windows/current'))
	}));
	const runs = createQuery(() => ({
		queryKey: ['mesh', 'runs'],
		queryFn: () => unwrap(api.GET('/v1/runs'))
	}));
	const savings = createQuery(() => ({
		queryKey: ['mesh', 'savings'],
		queryFn: () => unwrap(api.GET('/v1/savings'))
	}));

	// Settlement currency first, then alphabetical.
	const balances = $derived(
		[...(member.data?.balances ?? [])].sort((a, b) => {
			const settlement = member.data?.settlement_currency;
			if (a.currency === settlement) return -1;
			if (b.currency === settlement) return 1;
			return a.currency.localeCompare(b.currency);
		})
	);
</script>

<div class="flex flex-col gap-10">
	<PageHeader title={data.member.name} description="Your Mesh overview" />

	<Card>
		<dl class="grid grid-cols-1 gap-6 sm:grid-cols-3">
			<div class="flex flex-col gap-1">
				<dt class="text-body-default text-content-tertiary">Member state</dt>
				<dd class="text-body-large-bold text-content-primary">
					{humaniseStatus(member.data?.state ?? data.member.state)}
				</dd>
			</div>
			<div class="flex flex-col gap-1">
				<dt class="text-body-default text-content-tertiary">Settlement currency</dt>
				<dd class="text-body-large-bold text-content-primary">
					{member.data?.settlement_currency ?? data.member.settlement_currency}
				</dd>
			</div>
			<div class="flex flex-col gap-1">
				<dt class="text-body-default text-content-tertiary">Legal name</dt>
				<dd class="text-body-large-bold break-words text-content-primary">
					{member.data?.legal_name ?? '…'}
				</dd>
			</div>
		</dl>
	</Card>

	<Section title="Savings">
		{#snippet actions()}<Button href={resolve('/savings')} variant="link" size="sm"
				>View savings</Button
			>{/snippet}
		<Card class="bg-brand-pale">
			{#if savings.error}<p role="alert">
					{savings.error.message}
				</p>{:else if savings.data}<SavingsMeter totals={savings.data.totals} compact />{:else}<p
					aria-busy="true"
					class="text-content-tertiary"
				>
					Loading savings…
				</p>{/if}
		</Card>
	</Section>

	<Section title="Balances">
		{#if member.isPending}
			<p class="text-body-default text-content-tertiary" aria-busy="true">Loading balances…</p>
		{:else if member.isError}
			<div
				role="alert"
				class="flex items-center gap-3 rounded-card bg-background-neutral p-4 text-body-default text-content-primary"
			>
				<CircleAlert class="size-4 shrink-0 text-sentiment-negative" aria-hidden="true" />
				<p class="flex-1">We could not load your balances. {member.error.message}</p>
				<Button variant="secondary" size="sm" onclick={() => member.refetch()}>Try again</Button>
			</div>
		{:else if balances.length === 0}
			<EmptyState
				title="No balances yet"
				description="Balances appear once Wise funds your Mesh account."
			/>
		{:else}
			<ul class="grid grid-cols-[repeat(auto-fill,minmax(min(100%,300px),1fr))] gap-6">
				{#each balances as balance (balance.currency)}
					<Card element="li" class="flex flex-col gap-2">
						<span class="text-title-group text-content-secondary">{balance.currency}</span>
						<span class="text-amount text-content-primary">
							<Money money={balance.available} />
						</span>
						<span class="text-body-default text-content-tertiary">
							Available · <Money money={balance.held} /> held for settlement
						</span>
					</Card>
				{/each}
			</ul>
		{/if}
	</Section>

	<div class="grid grid-cols-1 gap-6 md:grid-cols-2">
		<Section title="Current window">
			<Card
				><p class="text-body-large-bold">{window.data?.eligible_count ?? '…'} eligible invoices</p>
				<p class="mt-2 text-content-tertiary">
					{window.data?.excluded_count ?? '…'} excluded from this window
				</p>
				{#if window.error}<p role="alert">{window.error.message}</p>{/if}<Button
					class="mt-5"
					href={resolve('/invoices')}
					variant="secondary">View invoices</Button
				></Card
			>
		</Section>
		<Section title="Open actions">
			<Card class="flex flex-col gap-4"
				>{#if data.me.role !== 'APPROVER'}<Button
						href={resolve('/confirmations')}
						variant="secondary">Review confirmation inbox</Button
					>{/if}{#each runs.data?.items.filter((r) => r.status === 'AWAITING_APPROVAL' && r.statement_id) ?? [] as r (r.id)}<Button
						href={resolve('/(member)/statements/[id]', { id: r.statement_id! })}
						>Review netting statement</Button
					>{/each}<Button href={resolve('/runs')} variant="link">View your runs</Button></Card
			>
		</Section>
	</div>
</div>
