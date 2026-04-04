/**
 * E2E tests for the invite flow (multi-user).
 *
 * Uses the custom userBContext fixture to simulate two simultaneous users.
 *
 * NOTE: Pending invites for users without a family are shown on the homepage (/),
 * not on /family (which shows CreateFamilyView for familyless users).
 */
import { expect, request as playwrightRequest } from '@playwright/test'
import { test } from '../fixtures/auth'
import { FamilyPage } from '../pages/family.page'
import { resetTestData, createFamilyViaApi } from '../fixtures/test-data'

const API_BASE = 'http://localhost:8000'

/** Shared state written by beforeEach and read by tests. */
let familyId: string

test.beforeEach(async () => {
  // Reset everything and rebuild state for each test.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await resetTestData(ctx)

  // Create User A and their family.
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  const family = await createFamilyViaApi(ctx, 'Invite Test Family')
  familyId = family.id

  // Pre-create User B so the invite endpoint can reference an existing account.
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'userb@e2e-test.com', display_name: 'User B' },
  })

  // Persist User A's session for the browser.
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  await ctx.storageState({ path: 'playwright/.auth/user.json' })
  await ctx.dispose()
})

// ---------------------------------------------------------------------------
// Single-user invite tests (User A sends, no browser switch needed)
// ---------------------------------------------------------------------------

test('admin can send an invite to an existing user', async ({ page }) => {
  const familyPage = new FamilyPage(page)
  await familyPage.goto()

  const [response] = await Promise.all([
    page.waitForResponse((res) => res.url().includes('/invites') && res.request().method() === 'POST'),
    familyPage.sendInvite('userb@e2e-test.com'),
  ])
  expect(response.status()).toBe(200)
})

test('invite to non-existent email shows same success response (privacy-preserving)', async ({ page }) => {
  const familyPage = new FamilyPage(page)
  await familyPage.goto()

  // Backend returns 200 regardless of whether the email exists (privacy-preserving).
  const [response] = await Promise.all([
    page.waitForResponse((res) => res.url().includes('/invites') && res.request().method() === 'POST'),
    familyPage.sendInvite('ghost@nowhere-e2e.com'),
  ])
  expect(response.status()).toBe(200)
})

// ---------------------------------------------------------------------------
// Multi-user invite tests (User A sends, User B accepts/declines)
// ---------------------------------------------------------------------------

/** Switch the browser page to User B's authenticated session. */
async function switchToUserB(
  page: import('@playwright/test').Page,
  userBContext: import('@playwright/test').APIRequestContext,
): Promise<void> {
  const loginRes = await userBContext.post('/api/auth/dev-login', {
    data: { email: 'userb@e2e-test.com', display_name: 'User B' },
  })
  expect(loginRes.ok()).toBeTruthy()
  const stateB = await userBContext.storageState()
  // addCookies replaces cookies with matching name+domain+path, effectively
  // switching the browser session from User A to User B.
  await page.context().addCookies(stateB.cookies)
}

test('invitee sees pending invite on homepage and can accept it', async ({ page, userBContext }) => {
  // 1. User A sends invite.
  const familyPage = new FamilyPage(page)
  await familyPage.goto()
  const [inviteRes] = await Promise.all([
    page.waitForResponse((res) => res.url().includes('/invites') && res.request().method() === 'POST'),
    familyPage.sendInvite('userb@e2e-test.com'),
  ])
  expect(inviteRes.status()).toBe(200)

  // 2. Switch browser to User B.
  await switchToUserB(page, userBContext)

  // 3. Pending invites are shown on the homepage for familyless users.
  await page.goto('/')
  await expect(page.getByText(/pending invites/i)).toBeVisible({ timeout: 10_000 })

  // 4. Accept the invite and verify the respond API returns 200.
  const [respondRes] = await Promise.all([
    page.waitForResponse((res) => res.url().includes('/respond') && res.request().method() === 'POST'),
    page.getByRole('button', { name: /accept/i }).first().click(),
  ])
  expect(respondRes.status()).toBe(200)

  // 5. After accepting, User B is now in the family → dashboard at /family.
  await familyPage.goto()
  await expect(page.getByRole('heading', { name: 'Invite Test Family', level: 1 })).toBeVisible({
    timeout: 10_000,
  })
})

test('invitee can decline an invite and remains familyless', async ({ page, userBContext }) => {
  // 1. User A sends invite.
  const familyPage = new FamilyPage(page)
  await familyPage.goto()
  const [inviteRes] = await Promise.all([
    page.waitForResponse((res) => res.url().includes('/invites') && res.request().method() === 'POST'),
    familyPage.sendInvite('userb@e2e-test.com'),
  ])
  expect(inviteRes.status()).toBe(200)

  // 2. Switch browser to User B.
  await switchToUserB(page, userBContext)

  // 3. Pending invites on homepage.
  await page.goto('/')
  await expect(page.getByText(/pending invites/i)).toBeVisible({ timeout: 10_000 })

  // 4. Decline.
  const [respondRes] = await Promise.all([
    page.waitForResponse((res) => res.url().includes('/respond') && res.request().method() === 'POST'),
    page.getByRole('button', { name: /decline/i }).first().click(),
  ])
  expect(respondRes.status()).toBe(200)

  // 5. User B is still familyless → /family shows create form.
  await familyPage.goto()
  await expect(familyPage.createFamilyForm).toBeVisible({ timeout: 10_000 })
})
