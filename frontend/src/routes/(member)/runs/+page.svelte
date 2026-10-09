<script lang="ts">
	import { localTime } from '$lib/dates';
	import { createQuery } from '@tanstack/svelte-query';
	import { resolve } from '$app/paths';
	import { api, activeRun } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import QueryState from '$lib/components/QueryState.svelte';
	import StatusChip from '$lib/components/StatusChip.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	const runs = createQuery(() => ({
		queryKey: ['mesh', 'runs'],
		queryFn: () => unwrap(api.GET('/v1/runs')),
		refetchInterval: (q) => (q.state.data?.items.some((r) => activeRun(r.status)) ? 5000 : false)
	}));
</script>

<svelte:head><title>Runs · Wise Mesh</title></svelte:head>
<div class="flex flex-col gap-8">
	<PageHeader
		title="Netting runs"
		description="Review your terms and follow each netting window through approval."
	/>
	<QueryState pending={runs.isPending} error={runs.error} retry={() => runs.refetch()} />
	{#if runs.data?.items.length}<div class="overflow-x-auto">
			<table class="w-full text-left">
				<thead
					><tr><th>Window closed</th><th>Status</th><th>Computation</th><th>Your statement</th></tr
					></thead
				><tbody
					>{#each runs.data.items as r (r.id)}<tr class="border-t border-content-primary/10"
							><td
								><a class="link-default" href={resolve('/(member)/runs/[id]', { id: r.id })}
									>{localTime(r.started_at)}</a
								></td
							><td><StatusChip kind="run" status={r.status} /></td><td>{r.current_attempt}</td><td
								>{#if r.statement_id}<a
										class="link-default"
										href={resolve('/(member)/statements/[id]', { id: r.statement_id })}
										>Review statement</a
									>{:else}No statement issued{/if}</td
							></tr
						>{/each}</tbody
				>
			</table>
		</div>{:else if runs.isSuccess}<EmptyState
			title="No runs yet"
			description="A run appears when Wise closes a window containing your confirmed invoices."
		/>{/if}
</div>
