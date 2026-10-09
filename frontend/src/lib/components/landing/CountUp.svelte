<script lang="ts">
	import { onMount } from 'svelte';

	interface Props {
		to: number;
		prefix?: string;
		suffix?: string;
		/** Milliseconds. */
		duration?: number;
	}

	let { to, prefix = '', suffix = '', duration = 1400 }: Props = $props();

	let el: HTMLSpanElement;
	let shown = $state(0);

	onMount(() => {
		if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
			shown = to;
			return;
		}
		let raf = 0;
		const io = new IntersectionObserver(([entry]) => {
			if (!entry.isIntersecting) return;
			io.disconnect();
			const start = performance.now();
			const tick = (now: number) => {
				const p = Math.min(1, (now - start) / duration);
				shown = Math.round(to * (1 - Math.pow(1 - p, 3)));
				if (p < 1) raf = requestAnimationFrame(tick);
			};
			raf = requestAnimationFrame(tick);
		});
		io.observe(el);
		return () => {
			cancelAnimationFrame(raf);
			io.disconnect();
		};
	});
</script>

<span bind:this={el} class="tabular-nums" aria-label="{prefix}{to}{suffix}"
	>{prefix}{shown}{suffix}</span
>
