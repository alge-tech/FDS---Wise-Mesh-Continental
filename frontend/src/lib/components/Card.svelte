<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { ClassValue, HTMLAttributes } from 'svelte/elements';

	interface Props extends Omit<HTMLAttributes<HTMLElement>, 'class' | 'children'> {
		/** 'marketing' uses the larger 32 px radius for landing-page cards. */
		variant?: 'default' | 'marketing';
		element?: 'div' | 'section' | 'article' | 'li';
		class?: ClassValue;
		children?: Snippet;
	}

	let {
		variant = 'default',
		element = 'div',
		class: className,
		children,
		...rest
	}: Props = $props();
</script>

<svelte:element
	this={element}
	{...rest}
	class={[
		'bg-background-screen p-6 ring-1 ring-content-primary/10',
		variant === 'marketing' ? 'rounded-card-lg' : 'rounded-card',
		className
	]}
>
	{@render children?.()}
</svelte:element>
