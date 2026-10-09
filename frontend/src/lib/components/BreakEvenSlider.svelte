<script lang="ts">
	import { createQuery, keepPreviousData } from '@tanstack/svelte-query';
	import { api } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import { formatBps } from '$lib/bps';
	import { minorToSafeNumber, MoneyParseError, parseDecimalToMinor } from '$lib/money';
	import { useCurrencies } from '$lib/stores/currencies.svelte';
	import Card from './Card.svelte';
	import Money from './Money.svelte';

	interface Props {
		/** Estimate from this run's real figures; without it the member types amounts in. */
		runId?: string | null;
		currency: string;
		standardRateBps?: number;
		feeShareBps?: number;
	}

	let { runId = null, currency, standardRateBps = 52, feeShareBps = 2500 }: Props = $props();

	const currencies = useCurrencies();
	// Sliders start at the price the statement used; the member then moves them freely.
	let rate = $state(52);
	let share = $state(2500);
	let gross = $state('100000.00');
	let net = $state('40000.00');
	let debounced = $state({ rate: 52, share: 2500 });
	$effect.pre(() => {
		rate = standardRateBps;
		share = feeShareBps;
	});
	$effect(() => {
		const next = { rate, share };
		const timer = setTimeout(() => (debounced = next), 200);
		return () => clearTimeout(timer);
	});

	const typed = $derived.by(() => {
		if (runId) return { ok: true as const, gross: 0, net: 0 };
		const exponent = currencies.exponentOf(currency);
		if (exponent === undefined) return { ok: false as const, message: '' };
		try {
			const g = minorToSafeNumber(parseDecimalToMinor(gross, exponent));
			const n = minorToSafeNumber(parseDecimalToMinor(net, exponent));
			if (n > g) return { ok: false as const, message: 'Net payable can’t exceed gross payable.' };
			return { ok: true as const, gross: g, net: n };
		} catch (e) {
			return { ok: false as const, message: e instanceof MoneyParseError ? e.message : '' };
		}
	});

	const estimate = createQuery(() => ({
		queryKey: [
			'mesh',
			'estimate',
			runId,
			debounced.rate,
			debounced.share,
			typed.ok ? typed.gross : null,
			typed.ok ? typed.net : null
		],
		queryFn: () =>
			unwrap(
				api.POST('/v1/estimates', {
					body: {
						standard_rate_bps: debounced.rate,
						fee_share_bps: debounced.share,
						...(runId
							? { run_id: runId }
							: typed.ok
								? { gross_payable_minor: typed.gross, net_payable_minor: typed.net }
								: {})
					}
				})
			),
		enabled: typed.ok,
		staleTime: Infinity,
		placeholderData: keepPreviousData
	}));
	const e = $derived(estimate.data);
</script>

<Card class="flex flex-col gap-6">
	<div class="flex flex-col gap-1">
		<h2 class="text-title-group">Break-even calculator</h2>
		<p class="text-body-default text-content-secondary">
			{runId
				? 'Uses your latest run. Move the sliders to see how the fee share and the standard transfer rate change what you keep.'
				: 'Enter what you owe in gross invoices and what you would pay after netting.'} Nothing is saved.
		</p>
	</div>
	{#if !runId}
		<div class="grid gap-5 sm:grid-cols-2">
			<label>Gross payables ({currency})<input bind:value={gross} inputmode="decimal" /></label>
			<label
				>Net payable after netting ({currency})<input bind:value={net} inputmode="decimal" /></label
			>
		</div>
		{#if !typed.ok && typed.message}<p role="alert" class="text-sentiment-negative">
				{typed.message}
			</p>{/if}
	{/if}
	<div class="grid gap-6 sm:grid-cols-2">
		<label
			>Mesh fee share · {formatBps(share)} of savings
			<input
				type="range"
				min="0"
				max="10000"
				step="500"
				bind:value={share}
				aria-valuetext={`${formatBps(share)} of savings`}
				class="accent-brand-forest"
			/>
		</label>
		<label
			>Standard transfer rate · {formatBps(rate)}
			<input
				type="range"
				min="0"
				max="200"
				step="1"
				bind:value={rate}
				aria-valuetext={formatBps(rate)}
				class="accent-brand-forest"
			/>
		</label>
	</div>
	{#if estimate.error}<p role="alert" class="text-sentiment-negative">
			{estimate.error.message}
		</p>{/if}
	{#if e}
		<p class="text-body-large-bold" aria-live="polite">
			{#if e.gross_savings.amount_minor > 0}
				You keep <Money money={e.savings} class="text-sentiment-positive" /> of the
				<Money money={e.gross_savings} /> that netting saves you.
			{:else}
				Netting saves nothing here, so there is no Mesh fee.
			{/if}
		</p>
		<dl class="grid grid-cols-2 gap-5 sm:grid-cols-4">
			<div>
				<dt class="text-content-tertiary">Paying gross would cost</dt>
				<dd class="text-body-large-bold"><Money money={e.baseline} /></dd>
			</div>
			<div>
				<dt class="text-content-tertiary">Mesh fee</dt>
				<dd class="text-body-large-bold"><Money money={e.fee} /></dd>
			</div>
			<div>
				<dt class="text-content-tertiary">Cost with Mesh</dt>
				<dd class="text-body-large-bold"><Money money={e.actual} /></dd>
			</div>
			<div>
				<dt class="text-content-tertiary">Your savings</dt>
				<dd class="text-body-large-bold text-sentiment-positive"><Money money={e.savings} /></dd>
			</div>
		</dl>
		<p class="text-body-default text-content-tertiary">
			{#if e.break_even_fee_share_bps}
				Break-even: Mesh would cost as much as paying gross only at a {formatBps(
					e.break_even_fee_share_bps
				)} fee share, because the fee is always a share of what you save.
			{:else}
				With no savings there is no break-even point to show.
			{/if}
			You move <Money money={e.net_payable} /> instead of <Money money={e.gross_payable} />.
		</p>
	{/if}
</Card>
