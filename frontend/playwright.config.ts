import { defineConfig, devices } from '@playwright/test';

// The app is served at http://localhost:3010 by either `bun run dev` or `docker compose up`.
// If something is already listening there, Playwright reuses it instead of starting the dev server.
export default defineConfig({
	testDir: 'e2e',
	testMatch: '**/*.spec.ts',
	fullyParallel: false,
	// Every spec shares one demo database (and the demo spec resets it), so run them in series.
	workers: 1,
	retries: process.env.CI ? 1 : 0,
	reporter: process.env.CI ? 'github' : 'list',
	use: {
		baseURL: 'http://localhost:3010',
		channel: process.env.PLAYWRIGHT_CHANNEL,
		trace: 'retain-on-failure'
	},
	projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
	webServer: {
		command: 'bun run dev',
		url: 'http://localhost:3010',
		reuseExistingServer: true,
		timeout: 60_000
	}
});
