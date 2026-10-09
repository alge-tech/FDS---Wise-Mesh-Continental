<script lang="ts" module>
	export type GlobePhase = 'invoices' | 'netting' | 'payments';
</script>

<script lang="ts">
	import { onMount } from 'svelte';
	import type * as Three from 'three';
	import {
		INVOICES,
		MEMBERS,
		PAYMENTS,
		type Flow,
		type MemberCode
	} from '$lib/landing/worked-example';

	interface Props {
		/** Called when the loop moves to a new step, for the caption drawn over the canvas. */
		onphase?: (phase: GlobePhase) => void;
	}

	let { onphase }: Props = $props();

	let host: HTMLDivElement;
	let canvas: HTMLCanvasElement;
	let labels: Partial<Record<MemberCode, HTMLSpanElement>> = $state({});

	// Loop timing, in seconds.
	const GROW = 2.2;
	const NET_AT = 6;
	const PAY_AT = 7.4;
	const FADE_AT = 13;
	const LOOP = 14;

	onMount(() => {
		let disposed = false;
		let cleanup = () => {};

		import('three').then((THREE) => {
			if (disposed) return;
			const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

			const R = 5;
			const LAT0 = 51 * (Math.PI / 180);
			const LON0 = 12 * (Math.PI / 180);

			const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
			renderer.setPixelRatio(Math.min(devicePixelRatio, 2));

			const scene = new THREE.Scene();
			const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
			camera.position.set(0, -2.3, R + 4.2);
			camera.lookAt(0, 0.55, R - 0.2);

			const globe = new THREE.Group();
			globe.rotation.order = 'XYZ';
			globe.rotation.set(LAT0, -LON0, 0);
			scene.add(globe);

			const toVec = (latDeg: number, lonDeg: number, r = R) => {
				const lat = (latDeg * Math.PI) / 180;
				const lon = (lonDeg * Math.PI) / 180;
				return new THREE.Vector3(
					r * Math.cos(lat) * Math.sin(lon),
					r * Math.sin(lat),
					r * Math.cos(lat) * Math.cos(lon)
				);
			};

			// Occluder so the far side of the dot sphere stays hidden.
			globe.add(
				new THREE.Mesh(
					new THREE.SphereGeometry(R * 0.995, 64, 64),
					new THREE.MeshBasicMaterial({ color: 0x163300 })
				)
			);

			// Dotted globe: an even Fibonacci lattice.
			const DOTS = 14000;
			const dotPos = new Float32Array(DOTS * 3);
			const golden = Math.PI * (3 - Math.sqrt(5));
			for (let i = 0; i < DOTS; i++) {
				const y = 1 - (i / (DOTS - 1)) * 2;
				const rad = Math.sqrt(1 - y * y);
				const t = golden * i;
				dotPos.set([Math.cos(t) * rad * R, y * R, Math.sin(t) * rad * R], i * 3);
			}
			const dotGeo = new THREE.BufferGeometry();
			dotGeo.setAttribute('position', new THREE.BufferAttribute(dotPos, 3));
			globe.add(
				new THREE.Points(
					dotGeo,
					new THREE.PointsMaterial({
						color: 0x9fe870,
						size: 0.028,
						transparent: true,
						opacity: 0.35
					})
				)
			);

			// Soft round glow texture, shared by nodes and particles.
			const glowCanvas = document.createElement('canvas');
			glowCanvas.width = glowCanvas.height = 64;
			const g = glowCanvas.getContext('2d')!;
			const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
			grad.addColorStop(0, 'rgba(255,255,255,1)');
			grad.addColorStop(0.25, 'rgba(255,255,255,0.6)');
			grad.addColorStop(1, 'rgba(255,255,255,0)');
			g.fillStyle = grad;
			g.fillRect(0, 0, 64, 64);
			const glowTex = new THREE.CanvasTexture(glowCanvas);

			const sprite = (color: number, scale: number) => {
				const s = new THREE.Sprite(
					new THREE.SpriteMaterial({
						map: glowTex,
						color,
						transparent: true,
						depthWrite: false,
						depthTest: false,
						opacity: 0.7,
						blending: THREE.AdditiveBlending
					})
				);
				s.scale.setScalar(scale);
				return s;
			};

			const nodePos = {} as Record<MemberCode, Three.Vector3>;
			const nodeHalo = {} as Record<MemberCode, Three.Sprite>;
			for (const m of MEMBERS) {
				const p = toVec(m.lat, m.lon, R + 0.01);
				nodePos[m.code] = p;
				const core = new THREE.Mesh(
					new THREE.SphereGeometry(0.045, 16, 16),
					new THREE.MeshBasicMaterial({ color: 0xe2f6d5 })
				);
				core.position.copy(p);
				const halo = sprite(0x9fe870, 0.32);
				halo.position.copy(p);
				globe.add(core, halo);
				nodeHalo[m.code] = halo;
			}

			interface Arc {
				curve: Three.QuadraticBezierCurve3;
				mesh: Three.Mesh<Three.TubeGeometry, Three.MeshBasicMaterial>;
				dots: Three.Sprite[];
				segments: number;
				delay: number;
			}

			const SEG = 64;
			const RADIAL = 6;
			const makeArcs = (flows: readonly Flow[], color: number, width: number, dotScale: number) =>
				flows.map((f, i): Arc => {
					const a = nodePos[f.from];
					const b = nodePos[f.to];
					const lift = R + 0.12 + a.distanceTo(b) * 0.28;
					const mid = a.clone().add(b).normalize().multiplyScalar(lift);
					const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
					const mesh = new THREE.Mesh(
						new THREE.TubeGeometry(curve, SEG, width, RADIAL, false),
						new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0 })
					);
					mesh.geometry.setDrawRange(0, 0);
					const dots = Array.from({ length: 3 }, () => sprite(color, dotScale));
					dots.forEach((d) => (d.visible = false));
					globe.add(mesh, ...dots);
					return { curve, mesh, dots, segments: SEG, delay: (i / flows.length) * 1.2 };
				});

			const invoiceArcs = makeArcs(INVOICES, 0xe2f6d5, 0.008, 0.16);
			const paymentArcs = makeArcs(PAYMENTS, 0x9fe870, 0.02, 0.32);

			const smooth = (x: number) => {
				const c = Math.min(1, Math.max(0, x));
				return c * c * (3 - 2 * c);
			};

			const drawArcs = (arcs: Arc[], t: number, opacity: number, speed: number) => {
				for (const arc of arcs) {
					const grow = smooth((t - arc.delay) / GROW);
					arc.mesh.geometry.setDrawRange(0, Math.floor(grow * arc.segments) * RADIAL * 6);
					arc.mesh.material.opacity = opacity * 0.85;
					arc.dots.forEach((dot, k) => {
						dot.visible = grow >= 1 && opacity > 0.01;
						if (!dot.visible) return;
						const u = (t * speed + k / arc.dots.length) % 1;
						dot.position.copy(arc.curve.getPoint(u));
						dot.material.opacity = opacity * Math.sin(u * Math.PI);
					});
				}
			};

			const tmp = new THREE.Vector3();
			const placeLabels = (w: number, h: number) => {
				for (const m of MEMBERS) {
					const el = labels[m.code];
					if (!el) continue;
					tmp.copy(nodePos[m.code]).applyMatrix4(globe.matrixWorld).project(camera);
					el.style.transform = `translate(${((tmp.x + 1) / 2) * w}px, ${((1 - tmp.y) / 2) * h}px)`;
				}
			};

			let width = 0;
			let height = 0;
			const resize = () => {
				width = host.clientWidth;
				height = host.clientHeight;
				renderer.setSize(width, height, false);
				camera.aspect = width / height;
				camera.updateProjectionMatrix();
			};
			resize();
			const ro = new ResizeObserver(resize);
			ro.observe(host);

			// Gentle parallax towards the pointer.
			let targetX = 0;
			let targetY = 0;
			const onPointer = (e: PointerEvent) => {
				const r = host.getBoundingClientRect();
				targetX = ((e.clientX - r.left) / r.width - 0.5) * 0.12;
				targetY = ((e.clientY - r.top) / r.height - 0.5) * 0.08;
			};
			window.addEventListener('pointermove', onPointer, { passive: true });

			let visible = true;
			const io = new IntersectionObserver(([entry]) => (visible = entry.isIntersecting));
			io.observe(host);

			const clock = new THREE.Clock();
			let phase: GlobePhase | undefined;
			let elapsed = reduced ? PAY_AT + GROW + 1 : 0;
			let raf = 0;

			const frame = () => {
				raf = requestAnimationFrame(frame);
				if (!visible) {
					clock.getDelta();
					return;
				}
				if (!reduced) elapsed += clock.getDelta();
				const t = elapsed % LOOP;

				globe.rotation.y +=
					(-LON0 + targetX + Math.sin(elapsed * 0.15) * 0.04 - globe.rotation.y) * 0.04;
				globe.rotation.x += (LAT0 + targetY - globe.rotation.x) * 0.04;

				const invOpacity = 1 - smooth((t - NET_AT) / 1.2);
				const payOpacity = smooth((t - PAY_AT) / 0.6) * (1 - smooth((t - FADE_AT) / 0.8));
				drawArcs(invoiceArcs, t, invOpacity, 0.35);
				drawArcs(paymentArcs, Math.max(0, t - PAY_AT), payOpacity, 0.28);

				// Nodes pulse while netting; the receiver swells once paid.
				const pulse = t > NET_AT && t < PAY_AT ? 1 + Math.sin(t * 14) * 0.25 : 1;
				for (const [code, halo] of Object.entries(nodeHalo)) {
					const receiver = PAYMENTS.some((p) => p.to === code);
					halo.scale.setScalar(0.32 * pulse * (receiver ? 1 + payOpacity * 0.9 : 1));
				}

				const next: GlobePhase = t < NET_AT ? 'invoices' : t < PAY_AT ? 'netting' : 'payments';
				if (next !== phase) onphase?.((phase = next));

				globe.updateMatrixWorld();
				placeLabels(width, height);
				renderer.render(scene, camera);
			};
			frame();

			cleanup = () => {
				cancelAnimationFrame(raf);
				ro.disconnect();
				io.disconnect();
				window.removeEventListener('pointermove', onPointer);
				scene.traverse((o) => {
					const obj = o as Three.Mesh;
					obj.geometry?.dispose();
					const mat = obj.material as Three.Material | undefined;
					mat?.dispose();
				});
				glowTex.dispose();
				renderer.dispose();
			};
		});

		return () => {
			disposed = true;
			cleanup();
		};
	});
</script>

<div bind:this={host} class="relative h-full w-full overflow-hidden" aria-hidden="true">
	<canvas bind:this={canvas} class="absolute inset-0 h-full w-full"></canvas>
	{#each MEMBERS as m (m.code)}
		<span
			bind:this={labels[m.code]}
			class="pointer-events-none absolute top-0 left-0 will-change-transform"
		>
			<span
				class="ml-3 -translate-y-1/2 rounded-pill bg-brand-forest/70 px-2 py-0.5 text-[11px] font-semibold tracking-wide whitespace-nowrap text-brand-pale/90 backdrop-blur-sm"
				style="display:inline-block"
			>
				{m.city}
			</span>
		</span>
	{/each}
</div>
