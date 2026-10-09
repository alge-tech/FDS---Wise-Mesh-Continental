<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import BrandLogo from '$lib/components/BrandLogo.svelte';
	import Button from '$lib/components/Button.svelte';
	import { useSessionHome } from '$lib/stores/session.svelte';

	let { children } = $props();
	const onLogin = $derived(page.url.pathname === '/login');
	const session = useSessionHome();
</script>

<div class="flex min-h-screen flex-col">
	<header class="mx-auto flex h-18 w-full max-w-[1200px] items-center justify-between px-6">
		<BrandLogo />
		{#if session.home}
			<Button href={resolve(session.home)} variant="secondary" size="sm">Open Mesh</Button>
		{:else if !onLogin}
			<Button href={resolve('/login')} variant="secondary" size="sm">Log in</Button>
		{/if}
	</header>
	<main class="mx-auto w-full max-w-[1200px] flex-1 px-6 pb-16">
		{@render children()}
	</main>
</div>
