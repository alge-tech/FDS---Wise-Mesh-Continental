<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { api, refreshMesh } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import { localTime } from '$lib/dates';
	import Button from '$lib/components/Button.svelte';
	import Card from '$lib/components/Card.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	let busy = $state(false);
	let error = $state('');
	let result = $state('');
	let confirm = $state(100);
	let dispute = $state(0);
	let seed = $state(1);
	let members = $state(6);
	let invoices = $state(30);
	let density = $state(50);
	let currency = $state('EUR');
	let resetting = $state(false);
	let fundingMember = $state('');
	let expireRun = $state('');
	const overview = createQuery(() => ({
		queryKey: ['mesh', 'admin'],
		queryFn: () => unwrap(api.GET('/v1/admin/overview'))
	}));
	const awaiting = $derived(
		overview.data?.runs.filter((r) => r.status === 'AWAITING_APPROVAL') ?? []
	);
	const chosenMember = $derived(overview.data?.members.find((m) => m.id === fundingMember));
	async function act(work: () => Promise<unknown>, describe?: (data: unknown) => string) {
		busy = true;
		error = '';
		result = '';
		try {
			const data = await work();
			result = describe ? describe(data) : JSON.stringify(data);
			await refreshMesh();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Demo action failed.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Demo controls · Wise Mesh</title></svelte:head>
<div class="flex flex-col gap-8">
	<PageHeader
		title="Demo controls"
		description="Reset, load invoice networks, simulate replies, and trigger the settlement failure paths."
	/>
	{#if error}<p role="alert" class="text-sentiment-negative">{error}</p>{/if}{#if result}<p
			role="status"
			class="rounded-card bg-brand-pale p-5 break-all"
		>
			{result}
		</p>{/if}
	<Card class="flex flex-col gap-5"
		><h2 class="text-title-group">Reset demo data</h2>
		<p>
			Deletes every invoice, run and ledger entry, then re-seeds members A to F, users, rates and
			opening balances. Use it before each demo.
		</p>
		{#if resetting}<div class="flex flex-wrap gap-3">
				<Button
					loading={busy}
					onclick={() =>
						act(
							() => unwrap(api.POST('/v1/demo/reset')),
							() => 'Demo data reset. Members A to F have their opening balances.'
						).then(() => (resetting = false))}>Delete everything and re-seed</Button
				><Button variant="link" onclick={() => (resetting = false)}>Cancel</Button>
			</div>{:else}<Button
				class="self-start"
				variant="secondary"
				disabled={busy}
				onclick={() => (resetting = true)}>Reset demo data</Button
			>{/if}</Card
	>
	<Card class="flex flex-col gap-5"
		><h2 class="text-title-group">Load a scenario</h2>
		<p>
			The worked example turns 8 invoices worth €450,000 into 3 transfers worth €80,000 after
			confirmation.
		</p>
		<div class="flex flex-wrap gap-3">
			<Button
				loading={busy}
				onclick={() =>
					act(() =>
						unwrap(
							api.POST('/v1/demo/scenarios/{name}', {
								params: { path: { name: 'worked_example' } }
							})
						)
					)}>Load worked example</Button
			><Button
				variant="secondary"
				disabled={busy}
				onclick={() =>
					act(() =>
						unwrap(
							api.POST('/v1/demo/scenarios/{name}', {
								params: { path: { name: 'improvement_example' } }
							})
						)
					)}>Load improvement example</Button
			>
		</div></Card
	>
	<Card
		><form
			class="flex flex-col gap-5"
			onsubmit={(e) => {
				e.preventDefault();
				act(() =>
					unwrap(
						api.POST('/v1/demo/simulate-confirmations', {
							body: { confirm_pct: confirm, dispute_pct: dispute, seed }
						})
					)
				);
			}}
		>
			<h2 class="text-title-group">Simulate replies</h2>
			<div class="grid gap-5 sm:grid-cols-3">
				<label
					>Confirm (%)<input type="number" min="0" max="100" bind:value={confirm} required /></label
				><label
					>Dispute (%)<input type="number" min="0" max="100" bind:value={dispute} required /></label
				><label>Seed<input type="number" bind:value={seed} required /></label>
			</div>
			<Button type="submit" loading={busy}>Simulate confirmations</Button>
		</form></Card
	>
	<Card
		><form
			class="flex flex-col gap-5"
			onsubmit={(e) => {
				e.preventDefault();
				act(() =>
					unwrap(
						api.POST('/v1/demo/generate', {
							body: { members, invoices, seed, cycle_density: density, currencies: [currency] }
						})
					)
				);
			}}
		>
			<h2 class="text-title-group">Generate a network</h2>
			<div class="grid gap-5 sm:grid-cols-2">
				<label
					>Members<input type="number" min="2" max="1000" bind:value={members} required /></label
				><label
					>Invoices<input type="number" min="1" max="20000" bind:value={invoices} required /></label
				><label
					>Cycle density (%)<input
						type="number"
						min="0"
						max="100"
						bind:value={density}
						required
					/></label
				><label
					>Currency<select bind:value={currency}
						>{#each ['EUR', 'USD', 'GBP', 'HUF', 'CNY'] as c (c)}<option>{c}</option>{/each}</select
					></label
				>
			</div>
			<Button type="submit" loading={busy}>Generate invoices</Button>
		</form></Card
	>
	<Card class="flex flex-col gap-5"
		><h2 class="text-title-group">Funding failure</h2>
		<p>
			Mark a payer as unable to fund. At the next Settle, prepare excludes it, recomputes the run
			and issues new statements.
		</p>
		<div class="flex flex-wrap items-end gap-3">
			<label
				>Member<select bind:value={fundingMember}>
					<option value="" disabled>Choose a member</option>
					{#each overview.data?.members ?? [] as m (m.id)}<option value={m.id}
							>{m.name}{m.funding_blocked ? ' · unable to fund' : ''}</option
						>{/each}
				</select></label
			>
			<Button
				disabled={busy || !chosenMember}
				onclick={() =>
					act(
						() =>
							unwrap(
								api.POST('/v1/demo/funding-failure', {
									body: { member_id: fundingMember, unable_to_fund: !chosenMember?.funding_blocked }
								})
							),
						(d) => {
							const state = d as { name: string; funding_blocked: boolean };
							return `${state.name} is ${state.funding_blocked ? 'unable to fund' : 'able to fund again'}.`;
						}
					)}>{chosenMember?.funding_blocked ? 'Restore funding' : 'Make unable to fund'}</Button
			>
		</div></Card
	>
	<Card class="flex flex-col gap-5"
		><h2 class="text-title-group">Expire approvals</h2>
		<p>
			Pass the approval deadline for a run: members who have not approved are removed and the run
			recomputes, up to the recompute limit.
		</p>
		{#if awaiting.length}<div class="flex flex-wrap items-end gap-3">
				<label
					>Run<select bind:value={expireRun}>
						<option value="" disabled>Choose a run</option>
						{#each awaiting as r (r.id)}<option value={r.id}
								>{localTime(r.started_at)} · computation {r.current_attempt}</option
							>{/each}
					</select></label
				>
				<Button
					disabled={busy || !expireRun}
					onclick={() =>
						act(
							() => unwrap(api.POST('/v1/demo/expire-approvals', { body: { run_id: expireRun } })),
							(d) => {
								const run = d as { status: string; current_attempt: number };
								return `Approvals expired. Run is ${run.status.toLowerCase().replaceAll('_', ' ')} at computation ${run.current_attempt}.`;
							}
						).then(() => (expireRun = ''))}>Expire approvals</Button
				>
			</div>{:else}<p class="text-content-tertiary">No run is waiting for approvals.</p>{/if}</Card
	>
</div>
