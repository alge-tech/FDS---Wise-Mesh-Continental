<script lang="ts">
	import { resolve } from '$app/paths';
	import type { Invoice } from '$lib/api/mesh';
	import Money from './Money.svelte';
	import StatusChip from './StatusChip.svelte';
	let { items }: { items: Invoice[] } = $props();
</script>

<div class="overflow-x-auto rounded-card ring-1 ring-content-primary/10">
	<table class="w-full min-w-[640px] text-left text-body-default">
		<thead class="bg-background-neutral"
			><tr
				><th>Invoice</th><th>Counterparty</th><th>Due date</th><th class="text-right"
					>Outstanding</th
				><th>Status</th></tr
			></thead
		>
		<tbody
			>{#each items as i (i.id)}<tr class="border-t border-content-primary/10">
					<td
						><a class="link-default" href={resolve('/(member)/invoices/[id]', { id: i.id })}
							>{i.invoice_number}</a
						><small class="block text-content-tertiary">Version {i.current_version}</small></td
					>
					<td>{i.counterparty}</td><td class="whitespace-nowrap">{i.due_date}</td>
					<td class="text-right"
						><Money money={{ amount_minor: i.outstanding_minor, currency: i.currency }} /></td
					><td><StatusChip kind="invoice" status={i.status} /></td>
				</tr>{/each}</tbody
		>
	</table>
</div>
