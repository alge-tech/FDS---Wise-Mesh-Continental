<script lang="ts" module>
	export type ButtonVariant = 'primary' | 'secondary' | 'link';
	export type ButtonSize = 'sm' | 'md' | 'lg';
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { ResolvedPathname } from '$app/types';
	import type { ClassValue, HTMLAnchorAttributes, HTMLButtonAttributes } from 'svelte/elements';
	import LoaderCircle from '@lucide/svelte/icons/loader-circle';

	interface CommonProps {
		variant?: ButtonVariant;
		size?: ButtonSize;
		/** Shows a spinner and blocks clicks; the label stays for screen readers. */
		loading?: boolean;
		disabled?: boolean;
		fullWidth?: boolean;
		class?: ClassValue;
		children: Snippet;
	}

	/** Internal links only: build `href` with resolve() from $app/paths. */
	type AnchorProps = CommonProps & { href: ResolvedPathname } & Omit<
			HTMLAnchorAttributes,
			'href' | 'class' | 'children'
		>;
	type NativeButtonProps = CommonProps & { href?: undefined } & Omit<
			HTMLButtonAttributes,
			'class' | 'children' | 'disabled'
		>;

	let {
		variant = 'primary',
		size = 'md',
		loading = false,
		disabled = false,
		fullWidth = false,
		class: className,
		children,
		href,
		...rest
	}: AnchorProps | NativeButtonProps = $props();

	const inactive = $derived(disabled || loading);

	const base =
		'inline-flex items-center justify-center gap-2 whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-content-primary';

	const variantClasses: Record<ButtonVariant, string> = {
		primary: 'rounded-pill bg-brand-primary text-brand-forest',
		secondary: 'rounded-pill border border-content-primary/15 bg-transparent text-content-primary',
		link: 'rounded-sm text-content-primary'
	};

	const hoverClasses: Record<ButtonVariant, string> = {
		primary: 'hover:brightness-95',
		secondary: 'hover:bg-content-primary/5',
		link: 'hover:text-content-secondary'
	};

	const sizeClasses: Record<ButtonVariant, Record<ButtonSize, string>> = {
		primary: {
			sm: 'h-8 px-4 text-body-default-bold',
			md: 'h-10 px-5 text-body-large-bold',
			lg: 'h-12 px-6 text-body-large-bold'
		},
		secondary: {
			sm: 'h-8 px-4 text-body-default-bold',
			md: 'h-10 px-5 text-body-large-bold',
			lg: 'h-12 px-6 text-body-large-bold'
		},
		link: { sm: 'link-default', md: 'link-large', lg: 'link-large' }
	};

	const classes = $derived([
		base,
		variantClasses[variant],
		sizeClasses[variant][size],
		inactive ? 'cursor-not-allowed opacity-50' : hoverClasses[variant],
		fullWidth && 'w-full',
		className
	]);
</script>

{#snippet content()}
	{#if loading}
		<LoaderCircle class="size-4 animate-spin" aria-hidden="true" />
	{/if}
	{@render children()}
{/snippet}

{#if href !== undefined}
	<a
		{...rest as HTMLAnchorAttributes}
		href={inactive ? undefined : href}
		role={inactive ? 'link' : undefined}
		aria-disabled={inactive ? 'true' : undefined}
		aria-busy={loading ? 'true' : undefined}
		class={classes}
	>
		{@render content()}
	</a>
{:else}
	{@const buttonRest = rest as HTMLButtonAttributes}
	<button
		{...buttonRest}
		type={buttonRest.type ?? 'button'}
		disabled={inactive}
		aria-busy={loading ? 'true' : undefined}
		class={classes}
	>
		{@render content()}
	</button>
{/if}
