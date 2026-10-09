<script lang="ts">
	import AppShell from '$lib/components/AppShell.svelte';
	import { memberNav } from '$lib/nav';

	let { data, children } = $props();
</script>

<AppShell me={data.me} nav={memberNav} context={data.member.name}>
	{@render children()}
</AppShell>
