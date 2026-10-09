<script lang="ts">
	import type { components } from '$lib/api/schema';
	import Money from './Money.svelte';

	type Total = components['schemas']['SavingsTotal'];

	interface Props {
		totals: Total[];
		/** Compact form for the dashboard: savings only, with the cost breakdown underneath. */
		compact?: boolean;
	}

	let { totals, compact = false }: Props = $props();
</script>

{#if totals.length === 0}
	<p class="text-body-default text-content-secondary">
		No settled runs yet. Savings appear here once a run settles.
	</p>
{:else}
	<ul class="flex flex-col gap-5">
		{#each totals as t (t.currency)}
			<li class="flex flex-col gap-2">
				<span class="text-amount text-sentiment-positive"><Money money={t.savings} /></span>
				<span class="text-body-default text-content-secondary">
					Saved across {t.runs} settled run{t.runs === 1 ? '' : 's'}, after the Mesh fee
				</span>
				<!-- Fees, baseline cost and savings always appear together. -->
				<dl
					class={[
						'grid gap-4 text-body-default',
						compact ? 'grid-cols-2' : 'grid-cols-2 sm:grid-cols-4'
					]}
				>
					<div>
						<dt class="text-content-tertiary">Paying gross would cost</dt>
						<dd class="text-body-default-bold"><Money money={t.baseline} /></dd>
					</div>
					<div>
						<dt class="text-content-tertiary">Mesh fee</dt>
						<dd class="text-body-default-bold"><Money money={t.fee} /></dd>
					</div>
					{#if !compact}
						<div>
							<dt class="text-content-tertiary">Cost with Mesh</dt>
							<dd class="text-body-default-bold"><Money money={t.actual} /></dd>
						</div>
						<div>
							<dt class="text-content-tertiary">Paid instead of gross</dt>
							<dd class="text-body-default-bold">
								<Money money={t.net_paid} /> of <Money money={t.gross_payable} />
							</dd>
						</div>
					{/if}
				</dl>
			</li>
		{/each}
	</ul>
{/if}
