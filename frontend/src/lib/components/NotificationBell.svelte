<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { DropdownMenu } from 'bits-ui';
	import Bell from '@lucide/svelte/icons/bell';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api, refreshMesh } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import { localTime } from '$lib/dates';

	const notifications = createQuery(() => ({
		queryKey: ['mesh', 'notifications'],
		queryFn: () => unwrap(api.GET('/v1/notifications', { params: { query: { limit: 10 } } })),
		refetchInterval: 15_000
	}));

	const text: Record<string, string> = {
		CONFIRMATION_REQUEST: 'A counterparty asks you to confirm an invoice',
		INVOICE_DISPUTED: 'A counterparty disputed one of your invoices',
		STATEMENT_READY: 'Your netting statement is ready to review',
		RECOMPUTATION: 'A run was recomputed; review your new statement',
		FUNDING_NEEDED: 'Settlement could not hold your funds; you left the run',
		SETTLEMENT_DONE: 'Settlement done: your run has settled',
		RUN_ABORTED: 'A run was cancelled; your invoices return to the next window',
		RUN_FALLBACK: 'A run fell back to gross payment'
	};

	const unread = $derived(notifications.data?.unread_count ?? 0);

	async function open(id: string, payload: Record<string, unknown>) {
		try {
			await unwrap(
				api.POST('/v1/notifications/{notification_id}/read', {
					params: { path: { notification_id: id } }
				})
			);
			await refreshMesh();
		} finally {
			if (typeof payload.run_id === 'string') {
				await goto(resolve('/(member)/runs/[id]', { id: payload.run_id }));
			} else if (typeof payload.invoice_id === 'string') {
				await goto(resolve('/(member)/invoices/[id]', { id: payload.invoice_id }));
			}
		}
	}
</script>

<DropdownMenu.Root>
	<DropdownMenu.Trigger
		class="relative inline-flex size-10 shrink-0 items-center justify-center rounded-pill border border-content-primary/15 text-content-primary hover:bg-content-primary/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-content-primary"
		aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
	>
		<Bell class="size-4" aria-hidden="true" />
		{#if unread}
			<span
				class="absolute -top-1 -right-1 inline-flex h-5 min-w-5 items-center justify-center rounded-pill bg-brand-primary px-1 text-body-default-bold text-brand-forest"
				aria-hidden="true">{unread > 9 ? '9+' : unread}</span
			>
		{/if}
	</DropdownMenu.Trigger>
	<DropdownMenu.Portal>
		<DropdownMenu.Content
			align="end"
			sideOffset={8}
			class="z-50 w-[340px] max-w-[calc(100vw-2rem)] rounded-card bg-background-screen p-2 ring-1 ring-content-primary/10"
		>
			<p class="px-3 py-2 text-title-group text-content-secondary">Notifications</p>
			{#each notifications.data?.items ?? [] as n (n.id)}
				<DropdownMenu.Item
					onSelect={() => open(n.id, n.payload)}
					class="flex cursor-pointer flex-col gap-0.5 rounded-[16px] px-3 py-2 outline-none data-highlighted:bg-background-neutral"
				>
					<span
						class={[
							'text-body-default',
							n.read_at ? 'text-content-secondary' : 'text-body-default-bold text-content-primary'
						]}>{text[n.type] ?? n.type.toLowerCase().replaceAll('_', ' ')}</span
					>
					<span class="text-body-default text-content-tertiary"
						>{n.read_at ? '' : 'New · '}{localTime(n.created_at)}</span
					>
				</DropdownMenu.Item>
			{:else}
				<p class="px-3 py-2 text-body-default text-content-tertiary">You’re all caught up.</p>
			{/each}
		</DropdownMenu.Content>
	</DropdownMenu.Portal>
</DropdownMenu.Root>
