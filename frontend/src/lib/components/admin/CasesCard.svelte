<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { api } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import { localTime } from '$lib/dates';
	import Card from '$lib/components/Card.svelte';

	const cases = createQuery(() => ({
		queryKey: ['mesh', 'cases'],
		queryFn: () => unwrap(api.GET('/v1/admin/cases'))
	}));
	const label: Record<string, string> = {
		SANCTIONS: 'Sanctions match',
		FUNDING: 'Funding failure',
		RING: 'Ring pattern',
		ENGINE_ALERT: 'Engine alert'
	};
</script>

<Card class="flex flex-col gap-4">
	<h2 class="text-title-group">Risk cases</h2>
	{#if cases.error}<p role="alert">{cases.error.message}</p>{/if}
	{#if cases.data?.items.length}
		<ul class="flex flex-col gap-3">
			{#each cases.data.items as c (c.id)}
				<li class="border-t border-content-primary/10 pt-3">
					<p class="text-body-default-bold">
						{label[c.type] ?? c.type} · {c.subject_name ?? c.subject_type.toLowerCase()} · {c.status.toLowerCase()}
					</p>
					<p class="text-body-default text-content-secondary">
						{c.notes ?? ''} Opened {localTime(c.created_at)}.
					</p>
				</li>
			{/each}
		</ul>
	{:else if cases.isSuccess}
		<p class="text-content-tertiary">No open cases. Screening and settlement open them here.</p>
	{/if}
</Card>
