<script lang="ts">
	import Button from './Button.svelte';
	let { pending, error, retry }: { pending: boolean; error?: Error | null; retry?: () => unknown } =
		$props();
</script>

{#if pending}<p aria-busy="true" class="text-content-tertiary">Loading…</p>{:else if error}
	<div role="alert" class="rounded-card bg-background-neutral p-5">
		<p>{error.message}</p>
		{#if retry}<Button variant="secondary" size="sm" onclick={retry}>Try again</Button>{/if}
	</div>
{/if}
