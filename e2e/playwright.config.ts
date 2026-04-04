import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright configuration for Monthly Budget e2e tests.
 *
 * reuseExistingServer is true locally (Tilt keeps services running) and
 * false in CI (fresh services are started per run).
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
