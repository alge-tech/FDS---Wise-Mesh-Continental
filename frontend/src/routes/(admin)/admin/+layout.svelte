<script lang="ts">
	import AppShell from '$lib/components/AppShell.svelte';
	import { adminNav } from '$lib/nav';

	let { data, children } = $props();
</script>

<AppShell me={data.me} nav={adminNav} context="Wise">
	{@render children()}
</AppShell>
