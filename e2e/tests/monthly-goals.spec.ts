/**
 * E2E tests for the monthly goals management workflow.
 *
 * Covers: admin sets goal via SetGoalDialog, progress bar updates after goal
 * is set, admin uses BulkGoalsEditor, rollover prompt appears and copies goals,
 * and member does not see goal management buttons.
 *
 * Each test resets state and re-authenticates to ensure isolation.
 */
import { test, expect, request as playwrightRequest } from '@playwright/test'
import { DashboardPage } from '../pages/dashboard.page'
import {
  resetTestData,
  createFamilyViaApi,
  createCategoryViaApi,
  createExpenseViaApi,
  createMonthlyGoalViaApi,
  sendInviteViaApi,
} from '../fixtures/test-data'

const API_BASE = 'http://localhost:8000'

/** Shared state set in beforeEach and consumed by each test. */
let familyId: string
let groceryCategoryId: string
let transportCategoryId: string

/** Current year-month string (YYYY-MM) used for test data. */
const CURRENT_MONTH = (() => {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  return `${year}-${month}`
})()

/** Previous month string (YYYY-MM) for rollover test data. */
const PREVIOUS_MONTH = (() => {
  const now = new Date()
  const date = new Date(now.getFullYear(), now.getMonth() - 1, 1)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  return `${year}-${month}`
})()

/** A date string (YYYY-MM-DD) for the first of the current month. */
const CURRENT_DATE = `${CURRENT_MONTH}-01`

test.beforeEach(async () => {
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await resetTestData(ctx)

  // Create primary admin user (User A) and their family.
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  const family = await createFamilyViaApi(ctx, 'Goals Test Family')
  familyId = family.id

  // Seed two categories.
  const grocery = await createCategoryViaApi(ctx, familyId, 'Groceries', '🛒')
  groceryCategoryId = grocery.id

  const transport = await createCategoryViaApi(ctx, familyId, 'Transport', '🚌')
  transportCategoryId = transport.id

  // Persist User A's session for the browser.
  await ctx.storageState({ path: 'playwright/.auth/user.json' })
  await ctx.dispose()
})

// ---------------------------------------------------------------------------
// 1. Admin sets a goal via SetGoalDialog and progress bar appears
// ---------------------------------------------------------------------------

test('admin sets a goal via SetGoalDialog and progress bar appears', async ({ page }) => {
  // Seed an expense so the category card is visible.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  await createExpenseViaApi(ctx, familyId, groceryCategoryId, 30000, 'Weekly shop', CURRENT_DATE)
  await ctx.dispose()

  const dashboard = new DashboardPage(page)
  await dashboard.goto()

  // Groceries category card should be visible.
  await expect(dashboard.categoryCard('Groceries')).toBeVisible({ timeout: 10_000 })

  // Admin should see the "Set Goal +" button (no goal exists yet).
  const setGoalBtn = page.getByTestId(`set-goal-btn-${groceryCategoryId}`)
  await expect(setGoalBtn).toBeVisible({ timeout: 5_000 })

  // Click the Set Goal button to open the dialog.
  await setGoalBtn.click()

  // The SetGoalDialog should open with the correct title.
  await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 5_000 })
  await expect(page.getByText('Set Goal — Groceries')).toBeVisible()

  // Enter a goal of $600.
  const amountInput = page.getByTestId('goal-amount-input')
  await expect(amountInput).toBeVisible({ timeout: 5_000 })
  await amountInput.fill('600.00')

  // Save the goal and wait for the API response.
  const [response] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/goals') &&
        res.request().method() === 'PUT',
    ),
    page.getByTestId('goal-save-btn').click(),
  ])
  expect(response.status()).toBe(200)

  // Dialog should close.
  await expect(page.locator('[role="dialog"]')).not.toBeVisible({ timeout: 5_000 })

  // The progress bar should now appear for Groceries (spending $300 of $600 = 50%).
  const progressBar = dashboard.categoryProgressIndicator('Groceries')
  await expect(progressBar).toBeVisible({ timeout: 10_000 })

  // The category card should display the goal amount.
  await expect(dashboard.categoryCard('Groceries')).toContainText('$600', { timeout: 5_000 })

  // The "Edit Goal" button should now appear in place of "Set Goal".
  const editGoalBtn = page.getByTestId(`edit-goal-btn-${groceryCategoryId}`)
  await expect(editGoalBtn).toBeVisible({ timeout: 5_000 })
})

// ---------------------------------------------------------------------------
// 2. Admin edits an existing goal via SetGoalDialog
// ---------------------------------------------------------------------------

test('admin edits an existing goal and sees updated progress bar', async ({ page }) => {
  // Seed a goal and expense via API.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  await createMonthlyGoalViaApi(ctx, familyId, groceryCategoryId, 60000, CURRENT_MONTH)
  await createExpenseViaApi(ctx, familyId, groceryCategoryId, 30000, 'Weekly groceries', CURRENT_DATE)
  await ctx.dispose()

  const dashboard = new DashboardPage(page)
  await dashboard.goto()

  // The "Edit Goal" button should be visible (goal already exists).
  const editGoalBtn = page.getByTestId(`edit-goal-btn-${groceryCategoryId}`)
  await expect(editGoalBtn).toBeVisible({ timeout: 10_000 })

  // Click to open the edit dialog.
  await editGoalBtn.click()
  await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 5_000 })
  await expect(page.getByText('Edit Goal — Groceries')).toBeVisible()

  // The amount field should be pre-populated with the existing goal.
  const amountInput = page.getByTestId('goal-amount-input')
  await expect(amountInput).toBeVisible({ timeout: 5_000 })

  // Update the goal to $1000.
  await amountInput.fill('1000.00')

  const [response] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/goals/') &&
        res.request().method() === 'PUT',
    ),
    page.getByTestId('goal-save-btn').click(),
  ])
  expect(response.status()).toBe(200)

  // Dialog should close and the updated goal amount should show.
  await expect(page.locator('[role="dialog"]')).not.toBeVisible({ timeout: 5_000 })
  await expect(dashboard.categoryCard('Groceries')).toContainText('$1,000', { timeout: 10_000 })
})

// ---------------------------------------------------------------------------
// 3. Admin uses BulkGoalsEditor to set goals for multiple categories
// ---------------------------------------------------------------------------

test('admin sets goals for all categories using BulkGoalsEditor', async ({ page }) => {
  // Seed expenses so both category cards appear.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  await createExpenseViaApi(ctx, familyId, groceryCategoryId, 5000, 'Grocery trip', CURRENT_DATE)
  await createExpenseViaApi(ctx, familyId, transportCategoryId, 2000, 'Bus pass', CURRENT_DATE)
  await ctx.dispose()

  const dashboard = new DashboardPage(page)
  await dashboard.goto()

  // The "Manage All Goals" button should be visible for admin.
  const manageBtn = page.getByTestId('manage-goals-btn')
  await expect(manageBtn).toBeVisible({ timeout: 10_000 })

  // Open the BulkGoalsEditor.
  await manageBtn.click()
  await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 5_000 })

  // Fill in goals for both categories.
  await page.getByTestId(`goal-input-${groceryCategoryId}`).fill('600.00')
  await page.getByTestId(`goal-input-${transportCategoryId}`).fill('150.00')

  // Save all goals and wait for the API response.
  const [response] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/goals') &&
        res.request().method() === 'PUT',
    ),
    page.getByTestId('bulk-goals-save-btn').click(),
  ])
  expect(response.status()).toBe(200)

  // Dialog should close.
  await expect(page.locator('[role="dialog"]')).not.toBeVisible({ timeout: 5_000 })

  // Both categories should now show their goal amounts.
  await expect(dashboard.categoryCard('Groceries')).toContainText('$600', { timeout: 10_000 })
  await expect(dashboard.categoryCard('Transport')).toContainText('$150', { timeout: 10_000 })
})

// ---------------------------------------------------------------------------
// 4. Rollover prompt appears and copies goals from previous month
// ---------------------------------------------------------------------------

test('rollover prompt appears and admin copies goals from previous month', async ({ page }) => {
  // Seed goals for the previous month but not the current month.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  await createMonthlyGoalViaApi(ctx, familyId, groceryCategoryId, 60000, PREVIOUS_MONTH)
  await createMonthlyGoalViaApi(ctx, familyId, transportCategoryId, 15000, PREVIOUS_MONTH)
  // Seed an expense for the current month so the budget-summary endpoint returns categories.
  await createExpenseViaApi(ctx, familyId, groceryCategoryId, 5000, 'Current shop', CURRENT_DATE)
  await ctx.dispose()

  const dashboard = new DashboardPage(page)
  await dashboard.goto()

  // The rollover prompt banner should be visible because:
  // - current month has no goals
  // - previous month has goals
  // - user is admin
  const rolloverPrompt = page.getByTestId('rollover-prompt')
  await expect(rolloverPrompt).toBeVisible({ timeout: 10_000 })

  // The "Copy from ..." button should be present.
  const copyBtn = page.getByTestId('rollover-copy-btn')
  await expect(copyBtn).toBeVisible({ timeout: 5_000 })

  // Click "Copy from [previous month]" and wait for the rollover API call.
  const [response] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/goals/rollover') &&
        res.request().method() === 'POST',
    ),
    copyBtn.click(),
  ])
  expect(response.status()).toBe(200)

  // After rollover the prompt should disappear.
  await expect(rolloverPrompt).not.toBeVisible({ timeout: 10_000 })

  // The copied goals should now be visible on the dashboard.
  await expect(dashboard.categoryCard('Groceries')).toContainText('$600', { timeout: 10_000 })
})

// ---------------------------------------------------------------------------
// 5. Rollover prompt "Start Fresh" dismisses the banner
// ---------------------------------------------------------------------------

test('admin dismisses rollover prompt by choosing Start Fresh', async ({ page }) => {
  // Seed goals for the previous month only.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  await createMonthlyGoalViaApi(ctx, familyId, groceryCategoryId, 60000, PREVIOUS_MONTH)
  await createExpenseViaApi(ctx, familyId, groceryCategoryId, 1000, 'Quick stop', CURRENT_DATE)
  await ctx.dispose()

  const dashboard = new DashboardPage(page)
  await dashboard.goto()

  // Rollover prompt should appear.
  const rolloverPrompt = page.getByTestId('rollover-prompt')
  await expect(rolloverPrompt).toBeVisible({ timeout: 10_000 })

  // Click "Start Fresh" to dismiss the banner.
  await page.getByTestId('rollover-start-fresh-btn').click()

  // Banner should disappear without making a rollover API call.
  await expect(rolloverPrompt).not.toBeVisible({ timeout: 5_000 })

  // No goals should have been created for the current month.
  const setGoalBtn = page.getByTestId(`set-goal-btn-${groceryCategoryId}`)
  await expect(setGoalBtn).toBeVisible({ timeout: 5_000 })
})

// ---------------------------------------------------------------------------
// 6. Member does not see goal management buttons
// ---------------------------------------------------------------------------

test('member sees category cards but not goal management buttons', async ({ page }) => {
  // Admin creates a goal for Groceries.
  const adminCtx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await adminCtx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  await createMonthlyGoalViaApi(adminCtx, familyId, groceryCategoryId, 60000, CURRENT_MONTH)
  await createExpenseViaApi(adminCtx, familyId, groceryCategoryId, 15000, 'Grocery run', CURRENT_DATE)

  // Pre-create User B so they can accept the invite.
  const memberCtx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await memberCtx.post('/api/auth/dev-login', {
    data: { email: 'userb@e2e-test.com', display_name: 'User B' },
  })

  // Send invite and have User B accept it.
  await sendInviteViaApi(adminCtx, familyId, 'userb@e2e-test.com')
  await adminCtx.dispose()

  const invitesRes = await memberCtx.get(`${API_BASE}/api/invites`)
  expect(invitesRes.ok()).toBeTruthy()
  const invites = (await invitesRes.json()) as Array<{ id: string }>
  expect(invites.length).toBeGreaterThan(0)
  const inviteId = invites[0].id

  const respondRes = await memberCtx.post(`${API_BASE}/api/invites/${inviteId}/respond`, {
    data: { action: 'accept' },
  })
  expect(respondRes.ok()).toBeTruthy()

  // Switch the browser to User B's session.
  const stateB = await memberCtx.storageState()
  await page.context().addCookies(stateB.cookies)
  await memberCtx.dispose()

  // Navigate fresh as User B.
  await page.goto('/')
  await page.waitForURL('/')

  // Groceries category card should be visible to the member.
  const dashboard = new DashboardPage(page)
  await expect(dashboard.categoryCard('Groceries')).toBeVisible({ timeout: 10_000 })

  // The progress bar should be visible (goal exists).
  const progressBar = dashboard.categoryProgressIndicator('Groceries')
  await expect(progressBar).toBeVisible({ timeout: 5_000 })

  // Goal edit/set buttons must NOT be visible to the member.
  await expect(page.getByTestId(`edit-goal-btn-${groceryCategoryId}`)).not.toBeVisible()
  await expect(page.getByTestId(`set-goal-btn-${groceryCategoryId}`)).not.toBeVisible()

  // "Manage All Goals" button must NOT be visible to the member.
  await expect(page.getByTestId('manage-goals-btn')).not.toBeVisible()
})
