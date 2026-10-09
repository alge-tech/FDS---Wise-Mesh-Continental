<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title: string;
		description?: string;
		actions?: Snippet;
	}

	let { title, description, actions }: Props = $props();
</script>

<div
	class="flex flex-col items-start gap-2 rounded-card bg-background-neutral p-6 text-body-default text-content-secondary"
>
	<p class="text-body-large-bold text-content-primary">{title}</p>
	{#if description}
		<p>{description}</p>
	{/if}
	{#if actions}
		<div class="mt-2 flex gap-3">{@render actions()}</div>
	{/if}
</div>
