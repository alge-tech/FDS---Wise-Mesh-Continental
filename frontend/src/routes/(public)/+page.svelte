<script lang="ts">
	import { resolve } from '$app/paths';
	import ArrowDown from '@lucide/svelte/icons/arrow-down';
	import Button from '$lib/components/Button.svelte';
	import CountUp from '$lib/components/landing/CountUp.svelte';
	import MeshGlobe, { type GlobePhase } from '$lib/components/landing/MeshGlobe.svelte';
	import NettingDiagram from '$lib/components/landing/NettingDiagram.svelte';
	import { GROSS, INVOICES, NET, PAYMENTS, SAVED_PCT } from '$lib/landing/worked-example';
	import { useSessionHome } from '$lib/stores/session.svelte';

	// Signed-in visitors keep their session: the calls to action go back into the app.
	const session = useSessionHome();
	const ctaHref = $derived(resolve(session.home ?? '/login'));
	const ctaLabel = $derived(session.home ? 'Open Mesh' : 'Log in');

	let phase: GlobePhase = $state('invoices');

	const caption: Record<GlobePhase, { big: string; small: string }> = {
		invoices: { big: `${INVOICES.length} invoices`, small: `€${GROSS}k in flight` },
		netting: { big: 'Netting…', small: 'circles cancel out' },
		payments: { big: `${PAYMENTS.length} payments`, small: `€${NET}k settled` }
	};

	const steps = [
		{ icon: 'upload', title: 'Upload & confirm', body: 'Only agreed debts get netted.' },
		{ icon: 'cycle', title: 'Net it out', body: 'Circles cancel. Every currency.' },
		{ icon: 'settle', title: 'Settle the rest', body: 'One approval. One Wise transfer.' }
	] as const;

	const currencies = ['EUR', 'GBP', 'HUF', 'NOK', 'USD', 'PLN', 'SEK', 'CZK', 'DKK', 'CHF', 'RON'];
</script>

<svelte:head><title>Wise Mesh Continental</title></svelte:head>

<!-- Hero: headline over a live 3D mesh of members netting their invoices -->
<section
	class="relative isolate mt-2 grid min-h-[620px] overflow-hidden rounded-card-lg bg-brand-forest md:grid-cols-[1fr_1.15fr]"
>
	<div class="relative z-10 flex flex-col items-start justify-center gap-7 p-8 md:p-14">
		<h1 class="text-hero text-brand-primary">Pay the difference, not every invoice</h1>
		<p class="max-w-[380px] text-body-large text-brand-pale/80">
			Mesh cancels out the debts between Europe's businesses. You settle one net amount.
		</p>
		<div class="flex flex-wrap items-center gap-3">
			<Button href={ctaHref} size="lg">{ctaLabel}</Button>
			<a
				href="#see-it-net"
				class="inline-flex h-12 items-center gap-2 rounded-pill px-5 text-body-large-bold text-brand-pale ring-1 ring-brand-pale/25 transition-colors hover:bg-brand-pale/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-primary"
			>
				See it net <ArrowDown class="size-4" aria-hidden="true" />
			</a>
		</div>
	</div>

	<div class="relative h-[380px] md:h-auto">
		<MeshGlobe onphase={(p) => (phase = p)} />
		<div
			class="pointer-events-none absolute top-4 right-4 rounded-[20px] bg-brand-forest/80 px-5 py-3 ring-1 ring-brand-primary/20 backdrop-blur-md md:top-auto md:right-6 md:bottom-6"
			aria-live="polite"
		>
			{#key phase}
				<div class="caption">
					<p class="text-screen-title text-brand-primary">{caption[phase].big}</p>
					<p class="text-body-default text-brand-pale/70">{caption[phase].small}</p>
				</div>
			{/key}
		</div>
	</div>
	<!-- fade the globe into the text column on wide screens -->
	<div
		class="pointer-events-none absolute inset-y-0 left-0 hidden w-1/2 bg-gradient-to-r from-brand-forest via-brand-forest/80 to-transparent md:block"
	></div>
</section>

<!-- Currency ticker -->
<div class="marquee mt-6 overflow-hidden" aria-hidden="true">
	<div class="flex w-max gap-3">
		{#each [...currencies, ...currencies] as code, i (i)}
			<span
				class="rounded-pill bg-background-neutral px-4 py-1.5 text-body-default-bold text-content-secondary"
			>
				{code}
			</span>
		{/each}
	</div>
</div>

<!-- Before / after -->
<section
	id="see-it-net"
	aria-labelledby="see-it-net-title"
	class="grid scroll-mt-8 grid-cols-1 items-center gap-12 py-20 md:grid-cols-[1fr_1.1fr]"
>
	<div class="flex flex-col gap-8">
		<h2
			id="see-it-net-title"
			class="text-[clamp(36px,4.5vw,56px)] leading-[0.95] font-black text-content-primary"
		>
			Debts run in circles.<br /><span class="text-sentiment-positive">We cut them.</span>
		</h2>
		<dl class="grid grid-cols-3 gap-3">
			<div class="rounded-card bg-brand-pale p-4">
				<dt class="text-body-default text-content-secondary">Payments</dt>
				<dd class="text-amount text-brand-forest">
					{INVOICES.length}→<CountUp to={PAYMENTS.length} duration={900} />
				</dd>
			</div>
			<div class="rounded-card bg-brand-pale p-4">
				<dt class="text-body-default text-content-secondary">Moved</dt>
				<dd class="text-amount text-brand-forest">€<CountUp to={NET} />k</dd>
				<dd class="text-body-default text-content-tertiary line-through">€{GROSS}k</dd>
			</div>
			<div class="rounded-card bg-brand-forest p-4">
				<dt class="text-body-default text-brand-pale/70">Saved</dt>
				<dd class="text-amount text-brand-primary"><CountUp to={SAVED_PCT} suffix="%" /></dd>
			</div>
		</dl>
	</div>
	<div class="mx-auto w-full max-w-[460px]">
		<NettingDiagram />
	</div>
</section>

<!-- How it works -->
<section aria-labelledby="how-it-works" class="flex flex-col gap-8 pb-20">
	<h2
		id="how-it-works"
		class="text-[clamp(32px,4vw,48px)] leading-[0.95] font-black text-content-primary"
	>
		Three steps. One payment.
	</h2>
	<ol class="grid grid-cols-1 gap-4 md:grid-cols-3">
		{#each steps as step, index (step.title)}
			<li
				class="group flex flex-col gap-5 rounded-card-lg bg-background-neutral p-7 transition-transform duration-300 hover:-translate-y-1"
			>
				<div class="flex items-center justify-between">
					<div class="grid size-20 place-items-center rounded-card bg-brand-forest">
						{#if step.icon === 'upload'}
							<svg viewBox="0 0 48 48" class="size-12" aria-hidden="true">
								<path d="M12 6h17l9 9v27H12z" fill="var(--color-brand-pale)" />
								<path d="M29 6v9h9" fill="var(--color-brand-primary)" />
								<path
									d="M18 29l5 5 9-11"
									class="tick"
									fill="none"
									stroke="var(--color-brand-forest)"
									stroke-width="3.5"
									stroke-linecap="round"
									stroke-linejoin="round"
									pathLength="1"
								/>
							</svg>
						{:else if step.icon === 'cycle'}
							<svg viewBox="0 0 48 48" class="size-12" aria-hidden="true">
								<g class="spin">
									<path
										d="M24 8a16 16 0 0 1 14 8"
										fill="none"
										stroke="var(--color-brand-primary)"
										stroke-width="4"
										stroke-linecap="round"
									/>
									<path
										d="M38 32a16 16 0 0 1-14 8"
										fill="none"
										stroke="var(--color-brand-primary)"
										stroke-width="4"
										stroke-linecap="round"
									/>
									<path
										d="M10 32a16 16 0 0 1 0-16"
										fill="none"
										stroke="var(--color-brand-primary)"
										stroke-width="4"
										stroke-linecap="round"
									/>
									<circle cx="24" cy="8" r="4" fill="var(--color-brand-pale)" />
									<circle cx="38" cy="32" r="4" fill="var(--color-brand-pale)" />
									<circle cx="10" cy="16" r="4" fill="var(--color-brand-pale)" />
								</g>
								<text
									x="24"
									y="25"
									text-anchor="middle"
									dominant-baseline="central"
									font-size="13"
									font-weight="900"
									fill="var(--color-brand-primary)">0</text
								>
							</svg>
						{:else}
							<svg viewBox="0 0 48 48" class="size-12" aria-hidden="true">
								<circle cx="10" cy="24" r="5" fill="var(--color-brand-pale)" />
								<circle cx="38" cy="24" r="7" fill="var(--color-brand-primary)" />
								<path
									d="M15 24h14"
									stroke="var(--color-brand-pale)"
									stroke-width="3"
									stroke-linecap="round"
									stroke-dasharray="2 4"
								/>
								<circle cx="16" cy="24" r="3.5" class="coin" fill="var(--color-brand-primary)" />
							</svg>
						{/if}
					</div>
					<span class="text-[64px] leading-none font-black text-content-primary/10">
						{index + 1}
					</span>
				</div>
				<div class="flex flex-col gap-1">
					<h3 class="text-screen-title text-content-primary">{step.title}</h3>
					<p class="text-body-large text-content-secondary">{step.body}</p>
				</div>
			</li>
		{/each}
	</ol>
</section>

<!-- Closing call to action -->
<section
	class="flex flex-col items-start justify-between gap-6 rounded-card-lg bg-brand-primary p-10 md:flex-row md:items-center md:p-14"
>
	<p class="text-[clamp(32px,4vw,52px)] leading-[0.95] font-black text-brand-forest">
		One net payment.<br />Every currency.
	</p>
	<a
		href={ctaHref}
		class="inline-flex h-12 items-center rounded-pill bg-brand-forest px-7 text-body-large-bold text-brand-primary transition-transform hover:scale-[1.03] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-forest"
	>
		{ctaLabel}
	</a>
</section>

<style>
	.caption {
		animation: rise 450ms cubic-bezier(0.34, 1.56, 0.64, 1);
	}
	@keyframes rise {
		from {
			opacity: 0;
			transform: translateY(8px);
		}
	}

	.marquee {
		mask-image: linear-gradient(90deg, transparent, #000 10%, #000 90%, transparent);
	}
	.marquee > div {
		animation: slide 30s linear infinite;
	}
	@keyframes slide {
		to {
			transform: translateX(calc(-50% - 6px));
		}
	}

	.tick {
		stroke-dasharray: 1;
		animation: draw 2.4s ease-in-out infinite;
	}
	@keyframes draw {
		0%,
		15% {
			stroke-dashoffset: 1;
		}
		45%,
		100% {
			stroke-dashoffset: 0;
		}
	}

	.spin {
		transform-origin: 24px 24px;
		animation: turn 4s linear infinite;
	}
	@keyframes turn {
		to {
			transform: rotate(360deg);
		}
	}

	.coin {
		animation: travel 1.8s cubic-bezier(0.65, 0, 0.35, 1) infinite;
	}
	@keyframes travel {
		0% {
			transform: translateX(0);
			opacity: 0;
		}
		15% {
			opacity: 1;
		}
		80% {
			transform: translateX(16px);
			opacity: 1;
		}
		100% {
			transform: translateX(18px);
			opacity: 0;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.caption,
		.marquee > div,
		.tick,
		.spin,
		.coin {
			animation: none;
		}
	}
</style>
