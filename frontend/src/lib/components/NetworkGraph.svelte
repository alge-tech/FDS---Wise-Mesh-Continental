<script lang="ts" module>
	export interface GraphSelection {
		nodes: { id: string; label: string; kind: string }[];
		edges: {
			id: string;
			source: string;
			target: string;
			currency: string;
			amount_minor: number;
			invoice_count?: number;
			kind: string;
		}[];
	}
</script>

<script lang="ts">
	import { onMount } from 'svelte';
	import type { Core, ElementDefinition, StylesheetJson } from 'cytoscape';
	import { formatMoney } from '$lib/money';
	import { useCurrencies } from '$lib/stores/currencies.svelte';

	interface Props extends GraphSelection {
		/** Accessible name of the graph, e.g. "Invoices before netting". */
		label: string;
		/** Where the text alternative is, e.g. "The table below lists every flow." */
		alternative?: string;
		height?: number;
	}

	let { nodes, edges, label, alternative = '', height = 460 }: Props = $props();

	const currencies = useCurrencies();
	let container: HTMLDivElement | undefined = $state();
	let cy: Core | null = $state(null);

	/** Colours come from the @theme tokens in app.css, never from literals in this file. */
	function token(name: string): string {
		return getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim();
	}

	function amountLabel(edge: GraphSelection['edges'][number]): string {
		const exponent = currencies.exponentOf(edge.currency);
		const amount =
			exponent === undefined
				? `${edge.currency} ${edge.amount_minor}`
				: formatMoney({ amount_minor: edge.amount_minor, currency: edge.currency }, exponent);
		return edge.invoice_count && edge.invoice_count > 1
			? `${amount} · ${edge.invoice_count} invoices`
			: amount;
	}

	function elements(): ElementDefinition[] {
		const max = Math.max(1, ...edges.map((e) => e.amount_minor));
		return [
			...nodes.map((n) => ({ data: { id: n.id, label: n.label, kind: n.kind } })),
			...edges.map((e) => ({
				data: {
					id: e.id,
					source: e.source,
					target: e.target,
					kind: e.kind,
					label: amountLabel(e),
					// Visual stroke width only; amounts themselves are never computed in floats.
					width: 2 + Math.round((e.amount_minor * 6) / max)
				}
			}))
		];
	}

	function stylesheet(): StylesheetJson {
		const forest = token('brand-forest');
		const primary = token('brand-primary');
		const pale = token('brand-pale');
		const neutral = token('background-neutral');
		const text = token('content-primary');
		const muted = token('content-tertiary');
		return [
			{
				selector: 'node',
				style: {
					label: 'data(label)',
					'background-color': primary,
					color: text,
					'font-family': 'Inter Variable, system-ui, sans-serif',
					'font-size': 13,
					'font-weight': 600,
					'text-valign': 'bottom',
					'text-margin-y': 8,
					width: 44,
					height: 44,
					'border-width': 2,
					'border-color': forest
				}
			},
			{
				selector: 'node[kind = "SELF"], node[kind = "MESH"]',
				style: { 'background-color': forest, 'border-color': primary, width: 56, height: 56 }
			},
			{
				selector: 'node[kind = "COUNTERPARTY"]',
				style: { 'background-color': neutral, 'border-color': muted }
			},
			{ selector: 'node[kind = "FX"]', style: { 'background-color': token('accent-cyan') } },
			{ selector: 'node[kind = "CARRY"]', style: { 'background-color': token('accent-orange') } },
			{
				selector: 'edge',
				style: {
					label: 'data(label)',
					width: 'data(width)',
					'curve-style': 'bezier',
					'target-arrow-shape': 'triangle',
					'line-color': muted,
					'target-arrow-color': muted,
					'font-size': 11,
					'font-weight': 600,
					color: text,
					'text-background-color': pale,
					'text-background-opacity': 1,
					'text-background-padding': '3px',
					'text-background-shape': 'roundrectangle',
					'text-rotation': 'autorotate'
				}
			},
			{
				selector: 'edge[kind = "SETTLEMENT"]',
				style: { 'line-color': forest, 'target-arrow-color': forest }
			},
			{
				selector: 'edge[kind = "FX_LEG"]',
				style: {
					'line-color': token('accent-cyan'),
					'target-arrow-color': token('accent-cyan'),
					'line-style': 'dashed'
				}
			}
		];
	}

	function render(instance: Core): void {
		instance.elements().remove();
		instance.add(elements());
		instance
			.layout({
				name: 'circle',
				// Stable positions: the same graph always draws the same way.
				sort: (a, b) => String(a.data('label')).localeCompare(String(b.data('label'))),
				padding: 48,
				animate: false
			})
			.run();
		instance.fit(undefined, 48);
	}

	onMount(() => {
		let disposed = false;
		let instance: Core | null = null;
		void import('cytoscape').then(({ default: cytoscape }) => {
			if (disposed || !container) return;
			instance = cytoscape({
				container,
				style: stylesheet(),
				userZoomingEnabled: false,
				userPanningEnabled: false,
				boxSelectionEnabled: false,
				autoungrabify: true
			});
			cy = instance;
		});
		return () => {
			disposed = true;
			instance?.destroy();
			cy = null;
		};
	});

	$effect(() => {
		// Re-render when the graph, or the currency exponents behind the labels, change.
		void nodes;
		void edges;
		void currencies.items;
		if (cy) render(cy);
	});
</script>

<figure class="flex flex-col gap-3">
	<div
		bind:this={container}
		role="img"
		aria-label={`${label}: ${nodes.length} parties and ${edges.length} flows. ${alternative}`.trim()}
		class="w-full rounded-card bg-background-screen ring-1 ring-content-primary/10"
		style:height={`${height}px`}
	></div>
	<figcaption class="sr-only">{label}</figcaption>
</figure>
