import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';
import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import type { ProxyOptions } from 'vite';

// Dev: the API runs on host port 3011. In docker-compose.dev.yml set API_PROXY_TARGET=http://api:8000.
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:3011';

// Keep the browser's Host header (changeOrigin: false) so the API's Origin check sees
// localhost:3010, exactly as it does behind nginx. xfwd adds X-Forwarded-For/Proto/Host.
const apiProxy: ProxyOptions = { target: apiTarget, changeOrigin: false, xfwd: true };
const proxy = { '/v1': apiProxy, '/healthz': apiProxy };

export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// SPA: no prerendered pages, every unknown path falls back to index.html.
			adapter: adapter({ pages: 'build', assets: 'build', fallback: 'index.html', strict: true }),
			// Absolute asset URLs so the fallback page works at nested routes such as /runs/123.
			paths: { relative: false }
		})
	],
	server: {
		port: 3010,
		strictPort: true,
		host: true,
		proxy,
		// Bind-mounted source in Docker on macOS may need polling: set VITE_USE_POLLING=1.
		watch: process.env.VITE_USE_POLLING ? { usePolling: true, interval: 300 } : undefined
	},
	preview: {
		port: 4173,
		strictPort: true,
		host: true,
		proxy
	},
	test: {
		expect: { requireAssertions: true },
		projects: [
			{
				extends: './vite.config.ts',
				test: {
					name: 'unit',
					environment: 'node',
					include: ['src/**/*.{test,spec}.{js,ts}'],
					exclude: ['src/**/*.svelte.{test,spec}.{js,ts}']
				}
			}
		]
	}
});
