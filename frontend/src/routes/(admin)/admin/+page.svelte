<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { api, activeRun, refreshMesh } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import type { components } from '$lib/api/schema';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import QueryState from '$lib/components/QueryState.svelte';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import AuditLog from '$lib/components/admin/AuditLog.svelte';
	import CasesCard from '$lib/components/admin/CasesCard.svelte';
	import LedgerCheckCard from '$lib/components/admin/LedgerCheckCard.svelte';
	import RunMonitorCard from '$lib/components/admin/RunMonitorCard.svelte';
	let { data } = $props();
	let closing = $state(false);
	let busy = $state(false);
	let reason = $state('');
	let error = $state('');
	let success = $state('');
	let switchTarget = $state<components['schemas']['KillRequest'] | null>(null);
	const overview = createQuery(() => ({
		queryKey: ['mesh', 'admin'],
		queryFn: () => unwrap(api.GET('/v1/admin/overview')),
		refetchInterval: (q) => (q.state.data?.runs.some((r) => activeRun(r.status)) ? 5000 : false)
	}));
	const window = createQuery(() => ({
		queryKey: ['mesh', 'window'],
		queryFn: () => unwrap(api.GET('/v1/windows/current'))
	}));
	async function closeWindow() {
		busy = true;
		error = '';
		success = '';
		try {
			const run = await unwrap(
				api.POST('/v1/admin/windows/current/close', { body: { reason_code: reason } })
			);
			closing = false;
			reason = '';
			success = `Window closed. Run is ${run.status.toLowerCase().replaceAll('_', ' ')}.`;
			await refreshMesh();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Close failed.';
		} finally {
			busy = false;
		}
	}
	function selectSwitch(memberId: string | null, enabled: boolean) {
		reason = '';
		switchTarget = {
			scope: memberId ? 'MEMBER' : 'GLOBAL',
			member_id: memberId,
			enabled,
			reason: ''
		};
	}
	async function saveSwitch() {
		if (!switchTarget) return;
		busy = true;
		error = '';
		success = '';
		try {
			await unwrap(api.PUT('/v1/admin/kill-switches', { body: { ...switchTarget, reason } }));
			switchTarget = null;
			reason = '';
			success = 'Kill switch updated.';
			await refreshMesh();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not save switch.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Ops console · Wise Mesh</title></svelte:head>
<div class="flex flex-col gap-8">
	<PageHeader
		title="Ops console"
		description="Close the window, settle or abort runs, control participation and check the ledger."
	/>
	<QueryState
		pending={overview.isPending}
		error={overview.error}
		retry={() => overview.refetch()}
	/>
	{#if error}<p role="alert" class="text-sentiment-negative">{error}</p>{/if}{#if success}<p
			role="status"
		>
			{success}
		</p>{/if}
	<Card class="flex flex-col gap-5"
		><h2 class="text-title-group">Current window</h2>
		<QueryState
			pending={window.isPending}
			error={window.error}
			retry={() => window.refetch()}
		/>{#if window.data}<p class="text-body-large-bold">
				{window.data.eligible_count} eligible invoices · {window.data.excluded_count} excluded
			</p>
			<p>
				Close freezes the agreed terms and exchange rates, screens members, and issues approval
				statements.
			</p>
			{#if data.me.role === 'WISE_OPS'}<Button
					disabled={busy ||
						!window.data.eligible_count ||
						overview.data?.kill_switches.some((k) => k.scope === 'GLOBAL' && k.enabled)}
					onclick={() => {
						closing = true;
						switchTarget = null;
						reason = '';
					}}>Close window</Button
				>{/if}{/if}
		{#if closing}<form
				class="flex flex-col gap-4"
				onsubmit={(e) => {
					e.preventDefault();
					closeWindow();
				}}
			>
				<label>Reason for closing<input bind:value={reason} required /></label>
				<div class="flex gap-3">
					<Button type="submit" loading={busy}>Freeze and compute</Button><Button
						variant="link"
						onclick={() => (closing = false)}>Cancel</Button
					>
				</div>
			</form>{/if}</Card
	>
	<section class="flex flex-col gap-5">
		<h2 class="text-title-group">Run monitor</h2>
		{#each overview.data?.runs ?? [] as r (r.id)}<RunMonitorCard
				run={r}
				role={data.me.role}
			/>{:else}<p class="text-content-tertiary">Close a window to start the first run.</p>{/each}
	</section>
	<Card class="flex flex-col gap-5"
		><h2 class="text-title-group">Kill switches</h2>
		<p>
			Every change requires a reason and is audited. A member switch excludes its invoices from the
			next window.
		</p>
		{#if overview.data}{@const global = overview.data.kill_switches.find(
				(k) => k.scope === 'GLOBAL'
			)}
			<div class="flex flex-wrap items-center justify-between gap-3">
				<p class="text-body-large-bold">
					Global switch · {global?.enabled ? 'Enabled' : 'Disabled'}
				</p>
				<Button
					variant="secondary"
					disabled={busy}
					onclick={() => {
						closing = false;
						selectSwitch(null, !global?.enabled);
					}}>{global?.enabled ? 'Disable global switch' : 'Enable global switch'}</Button
				>
			</div>
			{#each overview.data.members as m (m.id)}{@const enabled = overview.data.kill_switches.some(
					(k) => k.member_id === m.id && k.enabled
				)}
				<div
					class="flex flex-wrap items-center justify-between gap-3 border-t border-content-primary/10 pt-3"
				>
					<p>{m.name} · {enabled ? 'Excluded' : 'Participating'}</p>
					<Button
						variant="secondary"
						size="sm"
						disabled={busy}
						onclick={() => {
							closing = false;
							selectSwitch(m.id, !enabled);
						}}>{enabled ? 'Allow participation' : 'Exclude member'}</Button
					>
				</div>{/each}{/if}
		{#if switchTarget}<form
				class="flex flex-col gap-4"
				onsubmit={(e) => {
					e.preventDefault();
					saveSwitch();
				}}
			>
				<p>
					{switchTarget.enabled ? 'Enable' : 'Disable'}
					{switchTarget.scope.toLowerCase()} switch
				</p>
				<label>Reason for this change<input bind:value={reason} required /></label>
				<div class="flex gap-3">
					<Button type="submit" loading={busy}>Save switch</Button><Button
						variant="link"
						onclick={() => (switchTarget = null)}>Cancel</Button
					>
				</div>
			</form>{/if}</Card
	>
	<div class="grid gap-6 lg:grid-cols-2">
		{#if data.me.role === 'WISE_OPS'}<LedgerCheckCard />{/if}
		{#if data.me.role === 'WISE_COMPLIANCE'}<CasesCard />{/if}
	</div>
	<AuditLog runs={overview.data?.runs ?? []} />
</div>
