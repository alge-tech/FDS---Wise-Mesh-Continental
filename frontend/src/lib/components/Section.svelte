<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { ClassValue } from 'svelte/elements';

	interface Props {
		/** Section label in the title-group style; also the section's accessible name. */
		title: string;
		/** Optional controls aligned with the label, e.g. a "View all" link. */
		actions?: Snippet;
		class?: ClassValue;
		children: Snippet;
	}

	let { title, actions, class: className, children }: Props = $props();
	const headingId = $props.id();
</script>

<section aria-labelledby={headingId} class={['flex min-w-0 flex-col gap-3', className]}>
	<div class="flex min-h-8 items-center justify-between gap-4">
		<h2 id={headingId} class="text-title-group text-content-secondary">{title}</h2>
		{#if actions}
			<div class="flex items-center gap-2">{@render actions()}</div>
		{/if}
	</div>
	{@render children()}
</section>
