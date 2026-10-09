<script lang="ts">
	import { onMount } from 'svelte';
	import { INVOICES, PAYMENTS, type Flow, type MemberCode } from '$lib/landing/worked-example';

	interface Props {
		/** true shows the netted payments, false the raw invoices. */
		netted?: boolean;
	}

	let { netted = $bindable(false) }: Props = $props();

	const CX = 200;
	const CY = 180;
	const RING = 132;
	const NODE = 24;
	// Hexagon order chosen so few arrows cross.
	const ORDER: MemberCode[] = ['A', 'B', 'D', 'E', 'F', 'C'];
	const pos = Object.fromEntries(
		ORDER.map((code, i) => {
			const a = -Math.PI / 2 - Math.PI / 6 + (i * Math.PI) / 3;
			return [code, { x: CX + RING * Math.cos(a), y: CY + RING * Math.sin(a) }];
		})
	) as Record<MemberCode, { x: number; y: number }>;

	function arrow(f: Flow, head: number) {
		const a = pos[f.from];
		const b = pos[f.to];
		const dx = b.x - a.x;
		const dy = b.y - a.y;
		const len = Math.hypot(dx, dy);
		const ux = dx / len;
		const uy = dy / len;
		const bend = 22;
		const mx = (a.x + b.x) / 2 - uy * bend;
		const my = (a.y + b.y) / 2 + ux * bend;
		const sx = a.x + ux * NODE;
		const sy = a.y + uy * NODE;
		const ex = b.x - ux * (NODE + 6);
		const ey = b.y - uy * (NODE + 6);
		// Arrowhead along the curve's end tangent; the tip sits just off the node ring.
		const tl = Math.hypot(ex - mx, ey - my);
		const tx = (ex - mx) / tl;
		const ty = (ey - my) / tl;
		const px = ex + tx * 4;
		const py = ey + ty * 4;
		const bx = px - tx * head;
		const by = py - ty * head;
		const w = head * 0.6;
		return {
			d: `M${sx},${sy} Q${mx},${my} ${ex},${ey}`,
			head: `${px},${py} ${bx - ty * w},${by + tx * w} ${bx + ty * w},${by - tx * w}`,
			lx: (sx + 2 * mx + ex) / 4,
			ly: (sy + 2 * my + ey) / 4
		};
	}

	const invoiceArrows = INVOICES.map((f) => ({ f, ...arrow(f, 9) }));
	const paymentArrows = PAYMENTS.map((f) => ({ f, ...arrow(f, 14) }));

	let root: SVGSVGElement;
	let userPicked = false;

	function pick(value: boolean) {
		userPicked = true;
		netted = value;
	}

	onMount(() => {
		if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
		let timer: ReturnType<typeof setInterval> | undefined;
		const io = new IntersectionObserver(([entry]) => {
			clearInterval(timer);
			if (entry.isIntersecting && !userPicked) {
				timer = setInterval(() => {
					if (userPicked) clearInterval(timer);
					else netted = !netted;
				}, 3200);
			}
		});
		io.observe(root);
		return () => {
			clearInterval(timer);
			io.disconnect();
		};
	});
</script>

<div class="flex flex-col items-center gap-4">
	<div
		role="group"
		aria-label="Show"
		class="relative inline-flex rounded-pill bg-background-neutral p-1 text-body-default-bold"
	>
		<span
			class="absolute inset-y-1 left-1 w-[calc(50%-4px)] rounded-pill bg-brand-forest transition-transform duration-500 ease-[cubic-bezier(0.65,0,0.35,1)] motion-reduce:transition-none"
			style:transform={netted ? 'translateX(100%)' : 'none'}
		></span>
		{#each [false, true] as value (value)}
			<button
				type="button"
				aria-pressed={netted === value}
				onclick={() => pick(value)}
				class={[
					'relative z-10 w-32 rounded-pill py-2 transition-colors duration-500',
					netted === value ? 'text-brand-primary' : 'text-content-secondary'
				]}
			>
				{value ? '3 payments' : '8 invoices'}
			</button>
		{/each}
	</div>
	<svg
		bind:this={root}
		viewBox="0 0 400 360"
		class="h-auto w-full"
		role="img"
		aria-label={netted
			? 'Three net payments: A, C and E each pay F.'
			: 'Eight invoices running in circles between six members.'}
	>
		<g class="layer" class:off={netted}>
			{#each invoiceArrows as a, i (a.f.from + a.f.to)}
				<path
					d={a.d}
					class="flow"
					style="--i:{i}"
					fill="none"
					stroke="var(--color-content-tertiary)"
					stroke-width="1.75"
					pathLength="1"
				/>
				<polygon
					points={a.head}
					class="head"
					style="--i:{i}"
					fill="var(--color-content-tertiary)"
				/>
				<text x={a.lx} y={a.ly} class="amt" style="--i:{i}" fill="var(--color-content-secondary)">
					€{a.f.amount}k
				</text>
			{/each}
		</g>

		<g class="layer" class:off={!netted}>
			{#each paymentArrows as a, i (a.f.from + a.f.to)}
				<path
					d={a.d}
					class="flow"
					style="--i:{i}"
					fill="none"
					stroke="var(--color-brand-forest)"
					stroke-width="5"
					stroke-linecap="round"
					pathLength="1"
				/>
				<polygon points={a.head} class="head" style="--i:{i}" fill="var(--color-brand-forest)" />
				<rect
					x={a.lx - 24}
					y={a.ly - 13}
					width="48"
					height="22"
					rx="11"
					class="amt"
					style="--i:{i}"
					fill="var(--color-brand-primary)"
				/>
				<text x={a.lx} y={a.ly} class="amt bold" style="--i:{i}" fill="var(--color-brand-forest)">
					€{a.f.amount}k
				</text>
			{/each}
		</g>

		{#each ORDER as code (code)}
			{@const p = pos[code]}
			{@const receives = netted && PAYMENTS.some((f) => f.to === code)}
			{@const idle = netted && !PAYMENTS.some((f) => f.from === code || f.to === code)}
			<g class="node" class:idle style="transform-origin:{p.x}px {p.y}px">
				<circle
					cx={p.x}
					cy={p.y}
					r={NODE}
					fill={receives ? 'var(--color-brand-primary)' : 'var(--color-background-screen)'}
					stroke="var(--color-brand-forest)"
					stroke-width="2"
				/>
				<text x={p.x} y={p.y} class="label" fill="var(--color-brand-forest)">{code}</text>
			</g>
		{/each}
	</svg>
</div>

<style>
	.flow {
		stroke-dasharray: 1;
		stroke-dashoffset: 0;
		transition: stroke-dashoffset 700ms cubic-bezier(0.65, 0, 0.35, 1);
		transition-delay: calc(var(--i) * 70ms);
	}
	.head {
		transition: opacity 200ms ease;
		transition-delay: calc(550ms + var(--i) * 70ms);
	}
	.off .head {
		opacity: 0;
		transition-delay: 0ms;
	}
	.amt {
		transition: opacity 400ms ease;
		transition-delay: calc(300ms + var(--i) * 70ms);
	}
	.off .flow {
		stroke-dashoffset: 1;
		transition-delay: 0ms;
	}
	.off .amt {
		opacity: 0;
		transition-delay: 0ms;
	}
	text {
		font-size: 12px;
		font-weight: 500;
		text-anchor: middle;
		dominant-baseline: central;
	}
	text.bold {
		font-weight: 700;
	}
	text.label {
		font-size: 15px;
		font-weight: 800;
	}
	.node {
		transition:
			opacity 500ms ease,
			transform 500ms cubic-bezier(0.34, 1.56, 0.64, 1);
	}
	.node circle {
		transition: fill 500ms ease;
	}
	.node.idle {
		opacity: 0.35;
		transform: scale(0.85);
	}
	@media (prefers-reduced-motion: reduce) {
		.flow,
		.head,
		.amt,
		.node,
		.node circle {
			transition: none;
		}
	}
</style>
