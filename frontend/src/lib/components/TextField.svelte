<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';

	interface Props extends Omit<HTMLInputAttributes, 'value' | 'class' | 'id'> {
		label: string;
		value?: string;
		/** Field error; also marks the input aria-invalid and links it via aria-describedby. */
		error?: string;
		hint?: string;
	}

	let { label, value = $bindable(''), error, hint, ...rest }: Props = $props();

	const id = $props.id();
	const hintId = `${id}-hint`;
	const errorId = `${id}-error`;
	const describedBy = $derived(
		[hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined
	);
</script>

<div class="flex flex-col gap-2">
	<label for={id} class="text-body-default-bold text-content-primary">{label}</label>
	<input
		{...rest}
		{id}
		bind:value
		aria-invalid={error ? 'true' : undefined}
		aria-describedby={describedBy}
		class={[
			'h-12 rounded-xl bg-background-screen px-4 text-body-large text-content-primary ring-1 outline-none placeholder:text-content-tertiary focus:ring-2',
			error ? 'ring-sentiment-negative' : 'ring-content-primary/15 focus:ring-content-primary'
		]}
	/>
	{#if hint}
		<p id={hintId} class="text-body-default text-content-tertiary">{hint}</p>
	{/if}
	{#if error}
		<p id={errorId} class="text-body-default text-sentiment-negative">{error}</p>
	{/if}
</div>
