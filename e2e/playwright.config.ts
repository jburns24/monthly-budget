import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright configuration for Monthly Budget e2e tests.
 *
 * These tests require the k3d stack to be up (`task up`). Tilt port-forwards
 * 8000 -> backend and 5173 -> frontend, so the URLs below resolve and
 * reuseExistingServer short-circuits the webServer commands. The in-cluster
 * frontend proxies /api to http://backend:8000, and the backend pod gets
 * ANTHROPIC_MOCK=true from the dev overlay, which the receipt specs need.
 *
 * The webServer commands are only a fallback for a host-native run, and that
 * fallback no longer works on its own. Postgres is a cluster-internal Service
 * that the Tiltfile deliberately does not port-forward, so a host-native
 * uvicorn has no database to reach unless it is wrapped in
 * scripts/dev/pg_port_forward.sh; and the root .env leaves ANTHROPIC_MOCK
 * unset (it defaults to false), which makes the receipt specs fail in
 * confusing ways. Bring the stack up rather than relying on these commands.
 *
 * Note: no CI job runs this suite — the pre-commit `playwright-e2e` hook is
 * pre-push only, so the `process.env.CI` branches are effectively local-only.
 */
export default defineConfig({
  testDir: './tests',
  fullyParallel: false, // tests share DB state; run sequentially within a worker
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1, // single worker to avoid cross-test DB conflicts
  reporter: [['html', { outputFolder: 'playwright-report', open: 'never' }], ['list']],

  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    // Auth setup: authenticate once and save storage state
    {
      name: 'setup',
      testMatch: /.*\.setup\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },

    // Main test project — depends on setup completing first
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'playwright/.auth/user.json',
      },
      dependencies: ['setup'],
    },
  ],

  webServer: [
    {
      command: 'cd ../backend && uv run uvicorn app.main:app --port 8000',
      url: 'http://localhost:8000/api/health',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: 'cd ../frontend && npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
})
