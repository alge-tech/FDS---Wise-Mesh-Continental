<script lang="ts">
	import { createInfiniteQuery } from '@tanstack/svelte-query';
	import { api, type Run } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import { localTime } from '$lib/dates';
	import Button from '$lib/components/Button.svelte';
	import Card from '$lib/components/Card.svelte';

	interface Props {
		runs: Run[];
	}

	let { runs }: Props = $props();
	let runId = $state('');

	const events = createInfiniteQuery(() => ({
		queryKey: ['mesh', 'audit', runId],
		initialPageParam: null as string | null,
		queryFn: ({ pageParam }) =>
			unwrap(
				api.GET('/v1/admin/audit-events', {
					params: {
						query: {
							limit: 25,
							...(runId ? { run_id: runId } : {}),
							...(pageParam ? { cursor: pageParam } : {})
						}
					}
				})
			),
		getNextPageParam: (last) => last.next_cursor ?? null
	}));
	const rows = $derived(events.data?.pages.flatMap((p) => p.items) ?? []);
</script>

<Card class="flex flex-col gap-4">
	<div class="flex flex-wrap items-end justify-between gap-4">
		<div class="flex flex-col gap-1">
			<h2 class="text-title-group">Audit log</h2>
			<p class="text-body-default text-content-secondary">
				Every state change and staff action, newest first. Any run can be traced from these events.
			</p>
		</div>
		<label
			>Run<select bind:value={runId}>
				<option value="">All activity</option>
				{#each runs as r (r.id)}<option value={r.id}>{localTime(r.started_at)}</option>{/each}
			</select></label
		>
	</div>
	{#if events.error}<p role="alert">{events.error.message}</p>{/if}
	<div class="max-h-[480px] overflow-auto">
		<table class="w-full min-w-[640px] text-left text-body-default">
			<thead class="sticky top-0 bg-background-screen"
				><tr><th>When</th><th>Action</th><th>Actor</th><th>Reason</th></tr></thead
			>
			<tbody>
				{#each rows as e (e.id)}
					<tr class="border-t border-content-primary/10">
						<td class="whitespace-nowrap">{localTime(e.created_at)}</td>
						<td>{e.action.replaceAll('_', ' ')}</td>
						<td>{(e.actor_role ?? 'SYSTEM').toLowerCase().replaceAll('_', ' ')}</td>
						<td class="break-all">{e.reason_code ?? ''}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	{#if events.hasNextPage}
		<Button
			class="self-start"
			variant="secondary"
			size="sm"
			loading={events.isFetchingNextPage}
			onclick={() => events.fetchNextPage()}>Load more</Button
		>
	{/if}
</Card>
