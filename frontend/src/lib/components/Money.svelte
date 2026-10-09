<script lang="ts">
	import type { ClassValue } from 'svelte/elements';
	import { formatMoney, toMinorBigInt, type Money } from '$lib/money';
	import { useCurrencies } from '$lib/stores/currencies.svelte';

	interface Props {
		money: Money;
		/**
		 * Signed amounts show "+" for money received and use the positive colour for it.
		 * Negative amounts never turn red: paying is normal, not an error.
		 */
		signed?: boolean;
		locale?: string;
		class?: ClassValue;
	}

	let { money, signed = false, locale = 'en-GB', class: className }: Props = $props();

	const currencies = useCurrencies();
	const exponent = $derived(currencies.exponentOf(money.currency));
	const received = $derived(signed && toMinorBigInt(money.amount_minor) > 0n);
	const text = $derived(
		exponent === undefined
			? null
			: formatMoney(money, exponent, locale, { signDisplay: signed ? 'exceptZero' : 'auto' })
	);
</script>

{#if text !== null}
	<span
		class={['whitespace-nowrap tabular-nums', received && 'text-sentiment-positive', className]}
	>
		{text}
	</span>
{:else if currencies.isPending}
	<span class={['text-content-tertiary', className]} aria-busy="true">
		<span aria-hidden="true">…</span><span class="sr-only">Loading amount</span>
	</span>
{:else}
	<span class={['text-content-tertiary', className]}>{money.currency} amount unavailable</span>
{/if}
