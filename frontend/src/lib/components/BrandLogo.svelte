<script lang="ts">
	import { asset, resolve } from '$app/paths';

	interface Props {
		href?: '/' | '/dashboard' | '/admin';
	}

	let { href = '/' }: Props = $props();
</script>

<a
	href={resolve(href)}
	class="inline-flex items-center gap-2 rounded-sm text-content-primary focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-content-primary"
	aria-label="Wise Mesh, home"
>
	<img src={asset('/brand/flag.svg')} alt="" class="h-6 w-auto" width="86" height="84" />
	<img src={asset('/brand/wordmark.svg')} alt="" class="h-5 w-auto" width="479" height="166" />
	<span class="ml-1 border-l border-content-primary/15 pl-3 text-body-large-bold text-brand-forest">
		Mesh
	</span>
</a>
