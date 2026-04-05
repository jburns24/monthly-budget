/**
 * E2E tests for the full category lifecycle.
 *
 * Covers: create, edit, delete, seed defaults, and role-based visibility.
 * Each test resets state and re-authenticates to ensure isolation.
 */
import { test, expect, request as playwrightRequest } from '@playwright/test'
import { CategoriesPage } from '../pages/categories.page'
import {
  resetTestData,
  createFamilyViaApi,
  createCategoryViaApi,
  sendInviteViaApi,
} from '../fixtures/test-data'

const API_BASE = 'http://localhost:8000'

/** Shared state set in beforeEach and consumed by each test. */
let familyId: string

test.beforeEach(async () => {
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await resetTestData(ctx)

  // Create the primary admin user (User A) and their family.
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  const family = await createFamilyViaApi(ctx, 'Category Test Family')
  familyId = family.id

  // Persist User A's session for the browser.
  await ctx.storageState({ path: 'playwright/.auth/user.json' })
  await ctx.dispose()
})

// ---------------------------------------------------------------------------
// Admin: Create
// ---------------------------------------------------------------------------

test('admin creates a category and sees it in the list', async ({ page }) => {
  const categoriesPage = new CategoriesPage(page)
  await categoriesPage.goto()

  const [response] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/categories') &&
        res.request().method() === 'POST' &&
        !res.url().includes('/seed'),
    ),
    categoriesPage.createCategory('Groceries', '🛒'),
  ])
  expect(response.status()).toBe(201)

  // Category name should appear in the list after creation.
  await expect(page.getByText('Groceries')).toBeVisible({ timeout: 10_000 })
})

// ---------------------------------------------------------------------------
// Admin: Edit
// ---------------------------------------------------------------------------

test('admin edits a category name and sees the updated name', async ({ page }) => {
  // Seed the category via API so the test starts from a known state.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  await createCategoryViaApi(ctx, familyId, 'Old Name')
  await ctx.dispose()

  const categoriesPage = new CategoriesPage(page)
  await categoriesPage.goto()

  // Open the edit dialog for the category.
  await categoriesPage.editCategory('Old Name')

  // The edit dialog has a name field pre-filled with "Old Name".
  const nameInput = page.getByPlaceholder(/e\.g\. groceries/i)
  await expect(nameInput).toBeVisible()
  await nameInput.fill('New Name')

  const [response] = await Promise.all([
    page.waitForResponse(
      (res) => /\/categories\/[^/]+$/.test(res.url()) && res.request().method() === 'PUT',
    ),
    page.getByRole('button', { name: /save/i }).click(),
  ])
  expect(response.status()).toBe(200)

  // Updated name must appear; old name must not.
  await expect(page.getByText('New Name', { exact: true })).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('Old Name', { exact: true })).not.toBeVisible()
})

// ---------------------------------------------------------------------------
// Admin: Delete
// ---------------------------------------------------------------------------

test('admin deletes a category with no expenses and it disappears', async ({ page }) => {
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  await createCategoryViaApi(ctx, familyId, 'Dining')
  await ctx.dispose()

  const categoriesPage = new CategoriesPage(page)
  await categoriesPage.goto()

  const [response] = await Promise.all([
    page.waitForResponse(
      (res) => res.url().includes('/categories') && res.request().method() === 'DELETE',
    ),
    categoriesPage.deleteCategory('Dining'),
  ])
  expect(response.status()).toBe(200)

  // Category must no longer appear in the list.
  await expect(page.getByText('Dining')).not.toBeVisible({ timeout: 10_000 })
})

// ---------------------------------------------------------------------------
// Admin: Seed defaults
// ---------------------------------------------------------------------------

test('seed defaults creates 6 default categories', async ({ page }) => {
  const categoriesPage = new CategoriesPage(page)
  await categoriesPage.goto()

  // "Seed defaults" button is only rendered when the list is empty and the
  // user is an admin.
  await expect(categoriesPage.seedButton).toBeVisible({ timeout: 10_000 })

  const [response] = await Promise.all([
    page.waitForResponse(
      (res) => res.url().includes('/seed') && res.request().method() === 'POST',
    ),
    categoriesPage.seedDefaults(),
  ])
  expect(response.status()).toBe(200)

  // Expect all six default category names to appear.
  const defaultNames = ['Groceries', 'Dining', 'Transport', 'Entertainment', 'Bills', 'Other']
  for (const name of defaultNames) {
    await expect(page.getByText(name)).toBeVisible({ timeout: 10_000 })
  }
})

// ---------------------------------------------------------------------------
// Member: read-only view
// ---------------------------------------------------------------------------

test('member can view categories but cannot see admin action buttons', async ({ page }) => {
  // Admin (User A) creates a category.
  const adminCtx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await adminCtx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  await createCategoryViaApi(adminCtx, familyId, 'Transport')

  // Pre-create User B, then re-authenticate as User A to send the invite.
  const memberCtx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await memberCtx.post('/api/auth/dev-login', {
    data: { email: 'userb@e2e-test.com', display_name: 'User B' },
  })

  await sendInviteViaApi(adminCtx, familyId, 'userb@e2e-test.com')
  await adminCtx.dispose()

  // User B retrieves their pending invite id and accepts it.
  const invitesRes = await memberCtx.get(`${API_BASE}/api/invites`)
  expect(invitesRes.ok()).toBeTruthy()
  const invites = (await invitesRes.json()) as Array<{ id: string }>
  expect(invites.length).toBeGreaterThan(0)
  const inviteId = invites[0].id

  const respondRes = await memberCtx.post(`${API_BASE}/api/invites/${inviteId}/respond`, {
    data: { action: 'accept' },
  })
  expect(respondRes.ok()).toBeTruthy()

  // Switch the browser to User B's authenticated session. addCookies updates
  // the existing browser context so the next navigation uses User B's token.
  const stateB = await memberCtx.storageState()
  await page.context().addCookies(stateB.cookies)
  await memberCtx.dispose()

  const categoriesPage = new CategoriesPage(page)
  // Navigate fresh so React Query fetches /api/me under User B's session.
  await page.goto('/categories')
  await page.waitForURL('/categories')

  // Categories should be visible to the member.
  await expect(page.getByText('Transport')).toBeVisible({ timeout: 10_000 })

  // Admin-only action buttons must not be present for a member.
  await expect(categoriesPage.addButton).not.toBeVisible()
  await expect(categoriesPage.editButtons).toHaveCount(0)
  await expect(categoriesPage.deleteButtons).toHaveCount(0)
})
