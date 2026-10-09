<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api, activeRun, refreshMesh, statementContentSchema } from '$lib/api/mesh';
	import { ApiError, unwrap } from '$lib/api/client';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import QueryState from '$lib/components/QueryState.svelte';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import Money from '$lib/components/Money.svelte';
	let busy = $state(false);
	let rejectOpen = $state(false);
	let reason = $state('');
	let error = $state('');
	let success = $state('');
	let changedId = $state<string | null>(null);
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
	const content = $derived(
		statement.data ? statementContentSchema.safeParse(statement.data.content) : null
	);
	async function answer(decision: 'APPROVE' | 'REJECT') {
		if (!statement.data) return;
		busy = true;
		error = '';
		success = '';
		try {
			const run = await unwrap(
				api.POST('/v1/statements/{statement_id}/approvals', {
					params: { path: { statement_id: statement.data.id } },
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
</script>

<svelte:head><title>Netting statement · Wise Mesh</title></svelte:head>
<div class="flex flex-col gap-8">
	<QueryState
		pending={statement.isPending}
		error={statement.error}
		retry={() => statement.refetch()}
	/>
	{#if statement.data && content?.success}{@const s = statement.data}{@const c =
			content.data}<PageHeader
			title="Your netting statement"
			description="Review the exact terms before approving."
		/>
		<Card class="bg-brand-pale"
			><p class="text-body-large-bold">{c.summary}</p>
			<p class="mt-5 text-amount">
				<Money
					money={{ amount_minor: c.debit_minor || c.credit_minor, currency: c.settlement_currency }}
				/>
			</p>
			<p class="mt-2">{c.debit_minor ? 'Debit' : 'Credit'} · Mesh settlement</p>
			{#if c.carried_minor}<p>
					Carried to the next window: <Money
						signed
						money={{ amount_minor: c.carried_minor, currency: c.settlement_currency }}
					/>
				</p>{/if}</Card
		>
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
							><th>Invoice / Counterparty</th><th>Direction</th><th class="text-right">Gross</th><th
								class="text-right">Cancelled</th
							><th class="text-right">Residual</th></tr
						></thead
					><tbody
						>{#each c.invoices as i (i.invoice_id)}<tr class="border-t border-content-primary/10"
								><td
									><a
										class="link-default"
										href={resolve('/(member)/invoices/[id]', { id: i.invoice_id })}
										>{i.invoice_number}</a
									>
									<p class="text-content-tertiary">{i.counterparty}</p></td
								><td>{i.direction.toLowerCase()}</td><td class="text-right"
									><Money money={{ amount_minor: i.outstanding_minor, currency: i.currency }} /></td
								><td class="text-right"
									><Money money={{ amount_minor: i.cancelled_minor, currency: i.currency }} /></td
								><td class="text-right"
									><Money money={{ amount_minor: i.residual_minor, currency: i.currency }} /></td
								></tr
							>{/each}</tbody
					>
				</table>
			</div>
		</section>
		<Card
			><h2 class="mb-5 text-title-group">Fees and savings</h2>
			<dl class="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
				{#each [['Baseline cost', c.pricing.baseline_minor], ['Mesh fee', c.pricing.fee_minor], ['Actual cost', c.pricing.actual_minor], ['Your savings', c.pricing.net_benefit_minor]] as [label, amount] (label)}<div
					>
						<dt class="text-content-tertiary">{label}</dt>
						<dd class="text-body-large-bold">
							<Money money={{ amount_minor: Number(amount), currency: c.settlement_currency }} />
						</dd>
					</div>{/each}
			</dl>
			<p class="mt-4 text-content-tertiary">Price version {c.pricing.price_version}</p></Card
		>
		{#if c.fx_legs.length}<section>
				<h2 class="mb-4 text-title-group">Currency conversions</h2>
				{#each c.fx_legs as fx, index (index)}<p>
						<Money
							signed
							money={{ amount_minor: fx.from_amount_minor, currency: fx.from_currency }}
						/> to <Money
							signed
							money={{ amount_minor: fx.to_amount_minor, currency: fx.to_currency }}
						/> at {fx.rate}
					</p>{/each}
			</section>{/if}
		<Card class="flex flex-col gap-5"
			><p>{s.approval_count} of {s.required_approvers} approvals received.</p>
			{#if s.required_approvers === 2}<p>
					Two different approvers are required above your member’s threshold.
				</p>{/if}
			{#if s.can_approve}<div class="flex gap-3">
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
									: s.approval_count >= s.required_approvers
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
		</Card>{:else if statement.data && content && !content.success}<p role="alert">
			The statement could not be displayed. Reload the page.
		</p>{/if}
</div>
