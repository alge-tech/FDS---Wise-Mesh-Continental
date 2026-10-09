<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title: string;
		description?: string;
		actions?: Snippet;
	}

	let { title, description, actions }: Props = $props();
</script>

<svelte:head><title>{title} · Wise Mesh</title></svelte:head>

<header class="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
	<div class="flex min-w-0 flex-col gap-1">
		<h1 class="text-screen-title text-content-primary">{title}</h1>
		{#if description}
			<p class="text-body-large text-content-secondary">{description}</p>
		{/if}
	</div>
	{#if actions}
		<div class="flex items-center gap-3">{@render actions()}</div>
	{/if}
</header>
