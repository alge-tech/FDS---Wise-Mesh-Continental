<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { api, unwrap } from '$lib/api/client';
	import { memberQueryOptions, queryKeys } from '$lib/api/queries';
	import { queryClient } from '$lib/api/query-client';
	import { useCurrencies } from '$lib/stores/currencies.svelte';
	import {
		MoneyParseError,
		minorToDecimalString,
		minorToSafeNumber,
		parseDecimalToMinor
	} from '$lib/money';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import QueryState from '$lib/components/QueryState.svelte';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import TextField from '$lib/components/TextField.svelte';

	const member = createQuery(() => memberQueryOptions());
	const currencies = useCurrencies();

	let limit = $state('');
	let threshold = $state('');
	let currency = $state('');
	let loadedFor = $state<string | null>(null);
	let errors = $state<{ limit?: string; threshold?: string }>({});
	let error = $state('');
	let success = $state('');
	let busy = $state(false);

	// Fill the form once per load of the member, without overwriting the user's typing.
	$effect(() => {
		const m = member.data;
		if (!m || loadedFor === m.member_id) return;
		const exponent = currencies.exponentOf(m.settlement_currency);
		if (exponent === undefined) return;
		loadedFor = m.member_id;
		currency = m.settlement_currency;
		limit = m.payable_limit ? minorToDecimalString(m.payable_limit.amount_minor, exponent) : '';
		threshold = m.maker_checker_threshold
			? minorToDecimalString(m.maker_checker_threshold.amount_minor, exponent)
			: '';
	});

	function minorOrNull(text: string, exponent: number): number | null {
		return text.trim() === '' ? null : minorToSafeNumber(parseDecimalToMinor(text, exponent));
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		const m = member.data;
		const exponent = currencies.exponentOf(currency);
		if (!m || exponent === undefined) return;
		errors = {};
		error = '';
		success = '';
		let payable_limit_minor: number | null;
		let maker_checker_minor: number | null;
		try {
			payable_limit_minor = minorOrNull(limit, exponent);
		} catch (e) {
			errors.limit = e instanceof MoneyParseError ? e.message : 'Enter a valid amount';
			return;
		}
		try {
			maker_checker_minor = minorOrNull(threshold, exponent);
		} catch (e) {
			errors.threshold = e instanceof MoneyParseError ? e.message : 'Enter a valid amount';
			return;
		}
		busy = true;
		try {
			const updated = await unwrap(
				api.PATCH('/v1/members/me/settings', {
					body: {
						reason_code: 'SETTINGS_UPDATED',
						payable_limit_minor,
						maker_checker_minor,
						...(currency !== m.settlement_currency ? { settlement_currency: currency } : {})
					}
				})
			);
			queryClient.setQueryData(queryKeys.member, updated);
			await queryClient.invalidateQueries({ queryKey: queryKeys.me });
			success = 'Settings saved. They apply from the next netting computation.';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Settings could not be saved.';
		} finally {
			busy = false;
		}
	}
</script>

<div class="flex flex-col gap-8">
	<PageHeader
		title="Settings"
		description="Limits, maker-checker threshold, settlement currency and team."
	/>
	<QueryState pending={member.isPending} error={member.error} retry={() => member.refetch()} />
	{#if member.data}{@const m = member.data}
		<Card>
			<form class="flex max-w-xl flex-col gap-6" onsubmit={save}>
				<h2 class="text-title-group">Netting limits</h2>
				<div class="flex flex-col gap-2">
					<label for="settlement-currency" class="text-body-default-bold">Settlement currency</label
					>
					<select
						id="settlement-currency"
						bind:value={currency}
						class="h-12 rounded-xl bg-background-screen px-4 ring-1 ring-content-primary/15"
					>
						{#each currencies.items as c (c.code)}<option value={c.code}>{c.code}</option>{/each}
					</select>
					<p class="text-content-tertiary">
						Statements, holds and payouts use this currency. It can't change while one of your
						invoices is in an unfinished run.
					</p>
				</div>
				<TextField
					label="Payable limit per run"
					inputmode="decimal"
					bind:value={limit}
					error={errors.limit}
					hint={`In ${currency}. Leave empty for no limit. If your net payable is above it, you are left out of the run and the others are recomputed.`}
				/>
				<TextField
					label="Maker-checker threshold"
					inputmode="decimal"
					bind:value={threshold}
					error={errors.threshold}
					hint={`In ${currency}. Above it, two different approvers must approve a statement. Leave empty to turn it off.`}
				/>
				<div><Button type="submit" loading={busy}>Save settings</Button></div>
				{#if error}<p role="alert" class="text-sentiment-negative">{error}</p>{/if}
				{#if success}<p role="status">{success}</p>{/if}
			</form>
		</Card>
		<section>
			<h2 class="mb-4 text-title-group">Team</h2>
			<div class="overflow-x-auto">
				<table class="w-full text-left">
					<thead><tr><th>Name</th><th>Email</th><th>Role</th></tr></thead>
					<tbody>
						{#each m.team as u (u.user_id)}<tr class="border-t border-content-primary/10"
								><td>{u.display_name}</td><td>{u.email}</td><td
									>{u.role.replaceAll('_', ' ').toLowerCase()}</td
								></tr
							>{/each}
					</tbody>
				</table>
			</div>
		</section>
	{/if}
</div>
