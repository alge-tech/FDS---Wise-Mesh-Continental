<script lang="ts">
	import type { ClassValue } from 'svelte/elements';
	import { getStatusMeta, toneClasses, type StatusKind } from '$lib/status';

	interface Props {
		kind: StatusKind;
		status: string;
		class?: ClassValue;
	}

	let { kind, status, class: className }: Props = $props();
	const meta = $derived(getStatusMeta(kind, status));
</script>

<span
	class={[
		'inline-flex h-6 items-center rounded-pill px-3 text-body-default-bold whitespace-nowrap',
		toneClasses[meta.tone],
		className
	]}
	data-status={status}
>
	{meta.label}
</span>
