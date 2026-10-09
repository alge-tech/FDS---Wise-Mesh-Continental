<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import BrandLogo from '$lib/components/BrandLogo.svelte';
	import Button from '$lib/components/Button.svelte';
	import Card from '$lib/components/Card.svelte';

	const heading = $derived(
		page.status === 404
			? 'We could not find that page'
			: page.status === 403
				? 'You do not have access to this page'
				: 'Something went wrong'
	);
</script>

<svelte:head><title>{heading} · Wise Mesh</title></svelte:head>

<div class="mx-auto flex min-h-screen max-w-[1200px] flex-col gap-12 px-6 py-6">
	<header><BrandLogo /></header>
	<main class="flex flex-1 items-start justify-center pt-12">
		<Card class="flex w-full max-w-[560px] flex-col gap-4">
			<p class="text-title-group text-content-tertiary">Error {page.status}</p>
			<h1 class="text-screen-title text-content-primary">{heading}</h1>
			<p class="text-body-large text-content-secondary">{page.error?.message}</p>
			{#if page.error?.correlationId}
				<p class="text-body-default text-content-tertiary">
					Reference: <span class="font-mono">{page.error.correlationId}</span>
				</p>
			{/if}
			<div class="mt-2 flex gap-3">
				<Button href={resolve('/')}>Go to the home page</Button>
				<Button href={resolve('/login')} variant="secondary">Log in again</Button>
			</div>
		</Card>
	</main>
</div>
