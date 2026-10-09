<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api, activeRun, refreshMesh } from '$lib/api/mesh';
	import { ApiError, unwrap } from '$lib/api/client';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import QueryState from '$lib/components/QueryState.svelte';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import Money from '$lib/components/Money.svelte';
	import { localTime } from '$lib/dates';
	let busy = $state(false);
	let rejectOpen = $state(false);
	let reason = $state('');
	let error = $state('');
	let success = $state('');
	let changedId = $state<string | null>(null);
	let withdrawOpen = $state(false);
	let selected = $state<string[]>([]);
	let withdrawReason = $state('');
	const statement = createQuery(() => ({
		queryKey: ['mesh', 'statement', page.params.id],
		queryFn: () =>
			unwrap(
				api.GET('/v1/statements/{statement_id}', {
					params: { path: { statement_id: page.params.id! } }
				})
			),
		refetchInterval: (q) => (activeRun(q.state.data?.run_status) ? 5000 : false)
	}));
	async function answer(decision: 'APPROVE' | 'REJECT') {
		if (!statement.data) return;
		busy = true;
		error = '';
		success = '';
		try {
			const run = await unwrap(
				api.POST('/v1/statements/{statement_id}/approvals', {
					params: { path: { statement_id: statement.data.statement_id } },
					body: {
						decision,
						content_hash: statement.data.content_hash,
						...(reason ? { reason_code: reason } : {})
					}
				})
			);
			await refreshMesh();
			if (decision === 'REJECT') await goto(resolve('/(member)/runs/[id]', { id: run.id }));
			else success = 'Approval saved.';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Approval failed.';
			if (e instanceof ApiError && e.code === 'STATEMENT_CHANGED')
				changedId =
					typeof e.details.current_statement_id === 'string'
						? e.details.current_statement_id
						: null;
		} finally {
			busy = false;
		}
	}
	async function withdraw(event: SubmitEvent) {
		event.preventDefault();
		if (!statement.data || !selected.length) return;
		busy = true;
		error = '';
		try {
			const run = await unwrap(
				api.POST('/v1/runs/{run_id}/withdrawals', {
					params: { path: { run_id: statement.data.run_id } },
					body: { invoice_ids: selected, reason_code: withdrawReason }
				})
			);
			await refreshMesh();
			await goto(resolve('/(member)/runs/[id]', { id: run.id }));
		} catch (e) {
			error = e instanceof Error ? e.message : 'Withdrawal failed.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Netting statement · Wise Mesh</title></svelte:head>
<div class="flex flex-col gap-8">
	<QueryState
		pending={statement.isPending}
		error={statement.error}
		retry={() => statement.refetch()}
	/>
	{#if statement.data}{@const s = statement.data}<PageHeader
			title="Your netting statement"
			description="Review the exact terms before approving."
		/>
		<Card class="bg-brand-pale"
			><p class="text-body-large-bold">{s.summary}</p>
			<p class="mt-5 text-amount"><Money money={s.instruction.amount} /></p>
			<p class="mt-2">
				{s.instruction.type === 'DEBIT'
					? 'Debit'
					: s.instruction.type === 'CREDIT'
						? 'Credit'
						: 'No payment'} · {s.instruction.counterparty} · Reference {s.instruction.reference}
			</p>
			{#if s.carried.amount_minor}<p>
					Carried to the next window: <Money signed money={s.carried} />
				</p>{/if}</Card
		>
		<dl class="grid gap-5 sm:grid-cols-3">
			{#each [['Gross payable', s.gross_payable, false], ['Gross receivable', s.gross_receivable, false], ['Net position', s.net, true]] as const as [label, amount, signed] (label)}<div
				>
					<dt class="text-content-tertiary">{label}</dt>
					<dd class="text-body-large-bold"><Money {signed} money={amount} /></dd>
				</div>{/each}
		</dl>
		{#if !s.current}<div role="status" class="rounded-card bg-background-neutral p-5">
				<p>This statement was replaced after a recompute.</p>
				{#if s.current_statement_id}<Button
						href={resolve('/(member)/statements/[id]', { id: s.current_statement_id })}
						>Review current statement</Button
					>{/if}
			</div>{/if}
		<section>
			<h2 class="mb-4 text-title-group">Your invoices by counterparty</h2>
			<div class="overflow-x-auto">
				<table class="w-full text-left">
					<thead
						><tr
							>{#if withdrawOpen}<th><span class="sr-only">Withdraw</span></th>{/if}<th>Invoice</th
							><th>Direction</th><th class="text-right">Gross</th><th class="text-right"
								>Cancelled</th
							><th class="text-right">Residual</th></tr
						></thead
					>{#each s.counterparties as group (group.name)}<tbody
							><tr class="border-t border-content-primary/10"
								><th colspan={withdrawOpen ? 6 : 5} scope="rowgroup" class="text-body-default-bold"
									>{group.name}</th
								></tr
							>{#each group.invoices as i (i.invoice_id)}<tr
									class="border-t border-content-primary/10"
									>{#if withdrawOpen}<td
											><input
												type="checkbox"
												aria-label={`Withdraw ${i.invoice_number}`}
												value={i.invoice_id}
												bind:group={selected}
											/></td
										>{/if}<td
										><a
											class="link-default"
											href={resolve('/(member)/invoices/[id]', { id: i.invoice_id })}
											>{i.invoice_number}</a
										></td
									><td>{i.direction.toLowerCase()}</td><td class="text-right"
										><Money money={i.outstanding} /></td
									><td class="text-right"><Money money={i.cancelled} /></td><td class="text-right"
										><Money money={i.residual} /></td
									></tr
								>{/each}</tbody
						>{/each}
				</table>
			</div>
			{#if s.can_withdraw && !withdrawOpen}<div class="mt-4">
					<Button variant="secondary" onclick={() => (withdrawOpen = true)}
						>Withdraw invoices</Button
					>
				</div>{/if}
			{#if withdrawOpen}<form class="mt-4 flex max-w-xl flex-col gap-4" onsubmit={withdraw}>
					<p>
						Select the invoices to take out of this run, for example ones already paid outside Mesh.
						They return to the next window, and Mesh recomputes the run and issues new statements
						where terms change.
					</p>
					<label>Reason<input bind:value={withdrawReason} required /></label>
					<div class="flex gap-3">
						<Button type="submit" loading={busy} disabled={!selected.length}
							>Withdraw {selected.length}
							{selected.length === 1 ? 'invoice' : 'invoices'}</Button
						><Button
							variant="link"
							onclick={() => {
								withdrawOpen = false;
								selected = [];
							}}>Cancel</Button
						>
					</div>
				</form>{/if}
		</section>
		<Card
			><h2 class="mb-5 text-title-group">Fees and savings</h2>
			<dl class="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
				{#each [['Baseline cost', s.pricing.baseline], ['Mesh fee', s.fee], ['Actual cost', s.pricing.actual], ['Your savings', s.pricing.net_benefit]] as const as [label, amount] (label)}<div
					>
						<dt class="text-content-tertiary">{label}</dt>
						<dd class="text-body-large-bold"><Money money={amount} /></dd>
					</div>{/each}
			</dl>
			<p class="mt-4 text-content-tertiary">Price version {s.price_version}</p></Card
		>
		{#if s.fx_legs.length}<section>
				<h2 class="mb-4 text-title-group">Currency conversions</h2>
				{#each s.fx_legs as fx, index (index)}<p>
						<Money signed money={fx.from_amount} /> to <Money signed money={fx.to_amount} /> at {fx.rate}
					</p>{/each}
			</section>{/if}
		<Card class="flex flex-col gap-5"
			><p>
				{s.approval.approval_count} of {s.approval.required_approvers} approvals received. Approve by
				{localTime(s.approval.deadline)}.
			</p>
			{#if s.approval.required_approvers === 2}<p>
					Two different approvers are required above your member’s threshold.
				</p>{/if}
			{#if s.approval.can_approve}<div class="flex gap-3">
					<Button loading={busy} onclick={() => answer('APPROVE')}>Approve statement</Button><Button
						variant="secondary"
						disabled={busy}
						onclick={() => (rejectOpen = true)}>Reject statement</Button
					>
				</div>{:else}<p>
					{s.run_status === 'APPROVED'
						? 'All members have approved this run.'
						: s.run_status === 'PREPARED'
							? 'All members have approved. Funds are held for settlement.'
							: s.run_status === 'COMMITTED' && s.current
								? 'This run has settled. Only the net amount moved.'
								: s.run_status === 'ABORTED'
									? 'This run was cancelled. Your invoices return to the next window.'
									: s.approval.approval_count >= s.approval.required_approvers
										? 'Your statement has all required approvals. Waiting for the other members.'
										: 'No approval action is available for your role or this statement.'}
				</p>{/if}
			{#if rejectOpen}<form
					class="flex flex-col gap-4"
					onsubmit={(e) => {
						e.preventDefault();
						answer('REJECT');
					}}
				>
					<p>
						Rejecting removes your business from this run. Mesh will recompute the remaining
						invoices.
					</p>
					<label>Reason<input bind:value={reason} required /></label>
					<div class="flex gap-3">
						<Button type="submit" loading={busy}>Confirm rejection</Button><Button
							variant="link"
							onclick={() => (rejectOpen = false)}>Cancel</Button
						>
					</div>
				</form>{/if}
			{#if error}<p role="alert" class="text-sentiment-negative">
					{error}
				</p>{/if}{#if changedId}<Button
					href={resolve('/(member)/statements/[id]', { id: changedId })}
					>Review updated statement</Button
				>{/if}{#if success}<p role="status">{success}</p>{/if}
		</Card>{/if}
</div>
