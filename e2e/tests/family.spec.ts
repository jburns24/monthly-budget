/**
 * E2E tests for the family creation flow.
 *
 * Each test resets state and re-authenticates to ensure isolation.
 */
import { test, expect, request as playwrightRequest } from '@playwright/test'
import { FamilyPage } from '../pages/family.page'
import { resetTestData } from '../fixtures/test-data'

const API_BASE = 'http://localhost:8000'

test.beforeEach(async () => {
  // Reset and re-authenticate before each test so state is fully isolated.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await resetTestData(ctx)
  // Re-create the primary test user (reset wiped them).
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  // Persist new cookies for the browser.
  await ctx.storageState({ path: 'playwright/.auth/user.json' })
  await ctx.dispose()
})

test('user without a family sees the create-family form', async ({ page }) => {
  const familyPage = new FamilyPage(page)
  await familyPage.goto()

  await expect(familyPage.createFamilyForm).toBeVisible()
})

test('create a family and see the dashboard', async ({ page }) => {
  const familyPage = new FamilyPage(page)
  await familyPage.goto()

  // Intercept POST /api/families so we can assert it was called and succeeded.
  const [response] = await Promise.all([
    page.waitForResponse((res) => res.url().includes('/api/families') && res.request().method() === 'POST'),
    familyPage.createFamily('E2E Test Family'),
  ])
  expect(response.status()).toBe(201)

  // Reload to render the dashboard with fresh React Query state.
  await familyPage.goto()
  await expect(page.getByRole('heading', { name: 'E2E Test Family', level: 1 })).toBeVisible({
    timeout: 10_000,
  })
})

test('family dashboard shows creator as admin', async ({ page }) => {
  const familyPage = new FamilyPage(page)
  await familyPage.goto()

  // Wait for the create-family form to be rendered before interacting.
  await expect(familyPage.createFamilyForm).toBeVisible({ timeout: 10_000 })

  const [response] = await Promise.all([
    page.waitForResponse((res) => res.url().includes('/api/families') && res.request().method() === 'POST'),
    familyPage.createFamily('Admin Check Family'),
  ])
  expect(response.status()).toBe(201)

  await familyPage.goto()
  // The member list should contain User A with the Owner or Admin badge.
  await expect(page.locator('.chakra-badge').filter({ hasText: /owner|admin/i }).first()).toBeVisible({
    timeout: 10_000,
  })
})

test('user already in a family does not see the create form', async ({ page }) => {
  // Create the family first via API.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  await ctx.post('/api/families', { data: { name: 'Existing Family', timezone: 'UTC' } })
  await ctx.storageState({ path: 'playwright/.auth/user.json' })
  await ctx.dispose()

  const familyPage = new FamilyPage(page)
  await familyPage.goto()

  // The create form should NOT be visible.
  await expect(familyPage.createFamilyForm).not.toBeVisible({ timeout: 10_000 })
  // The dashboard should be shown instead.
  await expect(page.getByRole('heading', { name: 'Existing Family', level: 1 })).toBeVisible()
})
