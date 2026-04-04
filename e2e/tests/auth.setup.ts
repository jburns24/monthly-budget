/**
 * Playwright setup project: authenticate the primary test user and save
 * storageState so all tests in the "chromium" project inherit an authenticated
 * session automatically.
 *
 * Also resets all test data before the suite so each run starts clean.
 */
import { test as setup, expect } from '@playwright/test'
import path from 'path'

const AUTH_FILE = path.join(__dirname, '../playwright/.auth/user.json')
const API_BASE = 'http://localhost:8000'

setup('authenticate primary test user', async ({ request }) => {
  // 1. Wipe all test data so the suite starts from a clean slate.
  const resetRes = await request.post(`${API_BASE}/api/test/reset`)
  expect(resetRes.ok()).toBeTruthy()

  // 2. Log in as the primary test user via the dev-bypass endpoint.
  const loginRes = await request.post(`${API_BASE}/api/auth/dev-login`, {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  expect(loginRes.ok()).toBeTruthy()

  // 3. Persist cookies so the browser projects start authenticated.
  await request.storageState({ path: AUTH_FILE })
})
