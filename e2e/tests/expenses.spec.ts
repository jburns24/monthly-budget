/**
 * E2E tests for the full expense & dashboard lifecycle.
 *
 * Covers: create via FAB on dashboard, create via expenses page, edit, delete,
 * month selector filtering, dashboard progress colors, and multi-member visibility.
 * Each test resets state and re-authenticates to ensure isolation.
 */
import { test, expect, request as playwrightRequest } from '@playwright/test'
import { ExpensesPage } from '../pages/expenses.page'
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

/** A date string (YYYY-MM-DD) for the first of the current month. */
const CURRENT_DATE = `${CURRENT_MONTH}-01`

// ---------------------------------------------------------------------------
// Grace-period helpers
//
// The backend (backend/app/services/grace_period.py) treats a month as editable
// when it is the current month, or when fewer than `edit_grace_days` whole days
// have passed since the month ended. `edit_grace_days` defaults to 7 and is not
// settable through the API (backend/app/models/family.py).
//
// Everything below is derived from "now" so these tests keep passing as the
// calendar advances — never hardcode an absolute month here.
// ---------------------------------------------------------------------------

/** Backend default for `Family.edit_grace_days`. */
const GRACE_DAYS = 7

/** First day of the month `monthsBack` months before `now`. */
function monthStart(monthsBack: number): Date {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth() - monthsBack, 1)
}

/** Format a Date as YYYY-MM using local (not UTC) fields. */
function toYearMonth(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

/** Format a Date as YYYY-MM-DD using local (not UTC) fields. */
function toDateString(d: Date): string {
  return `${toYearMonth(d)}-${String(d.getDate()).padStart(2, '0')}`
}

/** The label the month selector renders, e.g. "March 2026". */
function toMonthLabel(d: Date): string {
  return d.toLocaleString('en-US', { month: 'long', year: 'numeric' })
}

/**
 * How many months back the most recent *still-editable* month is.
 *
 * The previous month stops being editable once `GRACE_DAYS` whole days have
 * passed since it ended, i.e. once today's day-of-month exceeds GRACE_DAYS + 1.
 * A one-day safety margin keeps the test off the boundary. When the previous
 * month is already expired the current month is used, which is always editable.
 */
const EDITABLE_MONTHS_BACK = new Date().getDate() <= GRACE_DAYS ? 1 : 0

/** A month comfortably past the grace period (months are >= 28 days long). */
const EXPIRED_MONTHS_BACK = 5

const EDITABLE_MONTH = monthStart(EDITABLE_MONTHS_BACK)
const EXPIRED_MONTH = monthStart(EXPIRED_MONTHS_BACK)

/** Click the month selector back `monthsBack` times. */
async function goBackMonths(
  pageObject: { goToPrevMonth: () => Promise<void> },
  monthsBack: number,
): Promise<void> {
  for (let i = 0; i < monthsBack; i++) {
    await pageObject.goToPrevMonth()
  }
}

test.beforeEach(async () => {
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await resetTestData(ctx)

  // Create primary admin user (User A) and their family.
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  const family = await createFamilyViaApi(ctx, 'Expense Test Family')
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
// 1. Create expense via FAB on dashboard
// ---------------------------------------------------------------------------

test('member creates expense via FAB on dashboard and sees it reflected', async ({ page }) => {
  const dashboard = new DashboardPage(page)
  await dashboard.goto()

  // Wait for the dashboard to load (FAB should be visible).
  await expect(dashboard.fabButton).toBeVisible({ timeout: 10_000 })

  // Click the FAB to open the Create Expense dialog.
  await dashboard.openCreateDialogViaFab()
  await expect(dashboard.dialogRoot).toBeVisible({ timeout: 5_000 })

  // Fill in the expense form.
  await dashboard.amountInput.fill('25.00')
  await dashboard.descriptionInput.fill('Coffee beans')
  await dashboard.categorySelect.selectOption(groceryCategoryId)
  await dashboard.dateInput.fill(CURRENT_DATE)

  // Submit and wait for the POST /expenses response.
  const [response] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/expenses') &&
        res.request().method() === 'POST' &&
        !res.url().includes('/seed'),
    ),
    dashboard.submitButton.click(),
  ])
  expect(response.status()).toBe(201)

  // Navigate to expenses page to verify the expense was created.
  const expensesPage = new ExpensesPage(page)
  await expensesPage.goto()

  // Wait for the expense list to appear with our new expense.
  await expect(page.getByText('Coffee beans')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('$25.00')).toBeVisible({ timeout: 5_000 })

  // Navigate back to dashboard and verify the total updated.
  await dashboard.goto()
  await expect(dashboard.totalSpent).toBeVisible({ timeout: 10_000 })
  // Dashboard total should reflect the new expense
  await expect(dashboard.totalSpent).toContainText('$25')
})

// ---------------------------------------------------------------------------
// 2. Create expense via expenses page
// ---------------------------------------------------------------------------

test('member creates expense via expenses page and sees it in filtered list', async ({ page }) => {
  const expensesPage = new ExpensesPage(page)
  await expensesPage.goto()

  // Wait for add expense button.
  await expect(expensesPage.addExpenseButton).toBeVisible({ timeout: 10_000 })

  // Open the create dialog via the header button.
  await expensesPage.openCreateDialog()
  await expect(expensesPage.dialogRoot).toBeVisible({ timeout: 5_000 })

  // Fill in the form.
  await expensesPage.amountInput.fill('12.00')
  await expensesPage.descriptionInput.fill('Bus fare')
  await expensesPage.categorySelect.selectOption(transportCategoryId)
  await expensesPage.dateInput.fill(CURRENT_DATE)

  // Submit and wait for API response.
  const [response] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/expenses') &&
        res.request().method() === 'POST' &&
        !res.url().includes('/seed'),
    ),
    expensesPage.submitButton.click(),
  ])
  expect(response.status()).toBe(201)

  // The new expense should appear in the current month's list.
  await expect(page.getByText('Bus fare')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('$12.00', { exact: true })).toBeVisible({ timeout: 5_000 })

  // Filter by Transport category — "Bus fare" should still appear.
  await expensesPage.filterByCategory(transportCategoryId)
  await expect(page.getByText('Bus fare')).toBeVisible({ timeout: 10_000 })

  // Filter by Groceries — "Bus fare" should disappear.
  await expensesPage.filterByCategory(groceryCategoryId)
  await expect(page.getByText('Bus fare')).not.toBeVisible({ timeout: 5_000 })
})

// ---------------------------------------------------------------------------
// 3. Edit expense
// ---------------------------------------------------------------------------

test('member edits an expense amount and description', async ({ page }) => {
  // Seed the expense via API.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  const expense = await createExpenseViaApi(ctx, familyId, groceryCategoryId, 2550, 'Coffee beans', CURRENT_DATE)
  await ctx.dispose()

  const expensesPage = new ExpensesPage(page)
  await expensesPage.goto()

  // Verify the original expense is visible.
  await expect(page.getByText('Coffee beans')).toBeVisible({ timeout: 10_000 })

  // Click the Edit button for this expense.
  await expensesPage.editExpense(expense.id)
  await expect(expensesPage.dialogRoot).toBeVisible({ timeout: 5_000 })

  // The edit dialog uses different test IDs (edit-expense-amount / edit-expense-description).
  const amountInput = page.getByTestId('edit-expense-amount')
  const descriptionInput = page.getByTestId('edit-expense-description')

  await expect(amountInput).toBeVisible({ timeout: 5_000 })

  // Update amount and description.
  await amountInput.fill('30.00')
  await descriptionInput.fill('Premium coffee beans')

  const [response] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/expenses/') &&
        res.request().method() === 'PUT',
    ),
    page.getByRole('button', { name: /save/i }).click(),
  ])
  expect(response.status()).toBe(200)

  // Updated values should be visible; old description should not.
  await expect(page.getByText('Premium coffee beans')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('$30.00')).toBeVisible({ timeout: 5_000 })
  await expect(page.getByText('Coffee beans', { exact: true })).not.toBeVisible()
})

// ---------------------------------------------------------------------------
// 4. Delete expense and verify dashboard totals decrease
// ---------------------------------------------------------------------------

test('member deletes an expense and it is removed from the list', async ({ page }) => {
  // Seed the expense via API.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  const expense = await createExpenseViaApi(ctx, familyId, transportCategoryId, 1200, 'Bus fare', CURRENT_DATE)
  await ctx.dispose()

  const expensesPage = new ExpensesPage(page)
  await expensesPage.goto()

  // Confirm expense is visible before deletion.
  await expect(page.getByText('Bus fare')).toBeVisible({ timeout: 10_000 })

  // Click the delete button for this expense.
  await expensesPage.deleteExpense(expense.id)
  await expect(expensesPage.dialogRoot).toBeVisible({ timeout: 5_000 })

  // Confirm deletion.
  const [response] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/expenses/') &&
        res.request().method() === 'DELETE',
    ),
    page.getByTestId('delete-expense-confirm').click(),
  ])
  expect(response.status()).toBe(200)

  // "Bus fare" should no longer appear in the list.
  await expect(page.getByText('Bus fare')).not.toBeVisible({ timeout: 10_000 })

  // Navigate to dashboard and verify the total no longer includes the deleted expense.
  const dashboard = new DashboardPage(page)
  await dashboard.goto()
  await expect(dashboard.totalSpent).toBeVisible({ timeout: 10_000 })
  // After deletion the total spent should be $0.
  await expect(dashboard.totalSpent).toContainText('$0')
})

// ---------------------------------------------------------------------------
// 5. Month selector filters expenses and dashboard by month
// ---------------------------------------------------------------------------

test('month selector filters expenses and dashboard by month', async ({ page }) => {
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })

  // Create an expense for current month.
  await createExpenseViaApi(ctx, familyId, groceryCategoryId, 5000, 'April purchase', CURRENT_DATE)

  // Create an expense for previous month.
  const prevMonth = (() => {
    const [year, month] = CURRENT_MONTH.split('-').map(Number)
    const date = new Date(year, month - 2, 1)
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
  })()
  const prevDate = `${prevMonth}-01`
  await createExpenseViaApi(ctx, familyId, groceryCategoryId, 3000, 'March purchase', prevDate)
  await ctx.dispose()

  // View dashboard for current month — should show current month expense.
  const dashboard = new DashboardPage(page)
  await dashboard.goto()
  await expect(dashboard.totalSpent).toBeVisible({ timeout: 10_000 })
  await expect(dashboard.totalSpent).toContainText('$50')

  // Navigate to previous month on dashboard.
  await dashboard.goToPrevMonth()
  // After month navigation the total should reflect the previous month ($30).
  await expect(dashboard.totalSpent).toContainText('$30', { timeout: 10_000 })

  // Also verify the expenses page month selector works.
  const expensesPage = new ExpensesPage(page)
  await expensesPage.goto()

  // The expenses page should default to current month and show "April purchase".
  await expect(page.getByText('April purchase')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('March purchase')).not.toBeVisible()

  // Navigate to previous month on expenses page.
  await expensesPage.goToPrevMonth()
  await expect(page.getByText('March purchase')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('April purchase')).not.toBeVisible()
})

// ---------------------------------------------------------------------------
// 6. Dashboard shows correct progress colors near goal threshold
// ---------------------------------------------------------------------------

test('dashboard shows yellow/orange progress color when spending is near goal', async ({ page }) => {
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })

  // Set a monthly goal of $100 for Groceries.
  await createMonthlyGoalViaApi(ctx, familyId, groceryCategoryId, 10000, CURRENT_MONTH)

  // Add an expense of $90 (90% of the goal — should trigger yellow/warning status).
  await createExpenseViaApi(ctx, familyId, groceryCategoryId, 9000, 'Big grocery run', CURRENT_DATE)
  await ctx.dispose()

  const dashboard = new DashboardPage(page)
  await dashboard.goto()

  // The Groceries category card should be visible.
  await expect(dashboard.categoryCard('Groceries')).toBeVisible({ timeout: 10_000 })

  // The progress bar for Groceries should show 90% usage.
  const progressBar = dashboard.categoryProgressIndicator('Groceries')
  await expect(progressBar).toBeVisible({ timeout: 5_000 })
  await expect(progressBar).toHaveAttribute('aria-label', /90% of budget used/)
})

// ---------------------------------------------------------------------------
// 7. Multiple family members can see each other's expenses
// ---------------------------------------------------------------------------

test("multiple family members can create and see each other's expenses", async ({ page }) => {
  // User A (admin) creates an expense.
  const adminCtx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await adminCtx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'Alice' },
  })
  await createExpenseViaApi(adminCtx, familyId, groceryCategoryId, 1500, "Alice's lunch", CURRENT_DATE)

  // Pre-create User B so they can accept the invite.
  const memberCtx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await memberCtx.post('/api/auth/dev-login', {
    data: { email: 'userb@e2e-test.com', display_name: 'Bob' },
  })

  // Admin sends invite to User B.
  await sendInviteViaApi(adminCtx, familyId, 'userb@e2e-test.com')
  await adminCtx.dispose()

  // User B accepts the invite.
  const invitesRes = await memberCtx.get(`${API_BASE}/api/invites`)
  expect(invitesRes.ok()).toBeTruthy()
  const invites = (await invitesRes.json()) as Array<{ id: string }>
  expect(invites.length).toBeGreaterThan(0)
  const inviteId = invites[0].id

  const respondRes = await memberCtx.post(`${API_BASE}/api/invites/${inviteId}/respond`, {
    data: { action: 'accept' },
  })
  expect(respondRes.ok()).toBeTruthy()

  // User B creates their own expense.
  await createExpenseViaApi(memberCtx, familyId, transportCategoryId, 800, "Bob's commute", CURRENT_DATE)

  // Switch the browser to User B's session.
  const stateB = await memberCtx.storageState()
  await page.context().addCookies(stateB.cookies)
  await memberCtx.dispose()

  // Navigate fresh so React Query fetches /api/me under User B's session.
  const expensesPage = new ExpensesPage(page)
  await page.goto('/expenses')
  await page.waitForURL('/expenses')

  // User B should see both their own and Alice's expenses.
  await expect(page.getByText("Alice's lunch")).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText("Bob's commute")).toBeVisible({ timeout: 5_000 })

  // Verify the user attribution shows the creator's name.
  // The ExpenseList renders display_name in a data-testid="expense-user-{id}" element.
  // Check expense user attributions — scoped to expense-user testids to avoid
  // matching the navbar which also shows the logged-in user's display name.
  await expect(page.locator('[data-testid^="expense-user-"]').filter({ hasText: 'Alice' })).toBeVisible({ timeout: 5_000 })
  await expect(page.locator('[data-testid^="expense-user-"]').filter({ hasText: 'Bob' })).toBeVisible({ timeout: 5_000 })
})

// ---------------------------------------------------------------------------
// 8. Grace period: edit succeeds within grace period
// ---------------------------------------------------------------------------

test('expense edit succeeds for a month still within the grace period', async ({ page }) => {
  // Seed an expense in the most recent month that is still inside the grace period.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  const expense = await createExpenseViaApi(
    ctx,
    familyId,
    groceryCategoryId,
    3000,
    'Editable groceries',
    toDateString(EDITABLE_MONTH),
  )
  await ctx.dispose()

  const expensesPage = new ExpensesPage(page)
  await expensesPage.goto()

  // Navigate back to the editable month (0 or 1 clicks depending on today's date).
  await goBackMonths(expensesPage, EDITABLE_MONTHS_BACK)
  await expect(expensesPage.monthDisplay).toContainText(toMonthLabel(EDITABLE_MONTH), {
    timeout: 5_000,
  })

  // The expense should be visible.
  await expect(page.getByText('Editable groceries')).toBeVisible({ timeout: 10_000 })

  // Click the edit button for the expense.
  await expensesPage.editExpense(expense.id)
  await expect(expensesPage.dialogRoot).toBeVisible({ timeout: 5_000 })

  // Update the amount.
  const amountInput = page.getByTestId('edit-expense-amount')
  await expect(amountInput).toBeVisible({ timeout: 5_000 })
  await amountInput.fill('35.00')

  // Submit — should succeed with HTTP 200.
  const [response] = await Promise.all([
    page.waitForResponse(
      (res) => res.url().includes('/expenses/') && res.request().method() === 'PUT',
    ),
    page.getByRole('button', { name: /save/i }).click(),
  ])
  expect(response.status()).toBe(200)

  // Updated amount should be visible.
  await expect(page.getByText('$35.00')).toBeVisible({ timeout: 10_000 })
})

// ---------------------------------------------------------------------------
// 9. Grace period: edit blocked after grace period expires
// ---------------------------------------------------------------------------

test('expense edit is blocked with 403 after the grace period has expired', async ({ page }) => {
  // Seed an expense in a month well beyond the grace period.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  const expense = await createExpenseViaApi(
    ctx,
    familyId,
    groceryCategoryId,
    2000,
    'Expired groceries',
    toDateString(EXPIRED_MONTH),
  )
  await ctx.dispose()

  const expensesPage = new ExpensesPage(page)
  await expensesPage.goto()

  // Navigate back to the expired month.
  await goBackMonths(expensesPage, EXPIRED_MONTHS_BACK)
  await expect(expensesPage.monthDisplay).toContainText(toMonthLabel(EXPIRED_MONTH), {
    timeout: 5_000,
  })

  // The expense should be visible.
  await expect(page.getByText('Expired groceries')).toBeVisible({ timeout: 10_000 })

  // Attempt edit — the API should return 403 (grace period expired).
  await expensesPage.editExpense(expense.id)
  await expect(expensesPage.dialogRoot).toBeVisible({ timeout: 5_000 })

  const amountInput = page.getByTestId('edit-expense-amount')
  await expect(amountInput).toBeVisible({ timeout: 5_000 })
  await amountInput.fill('25.00')

  const [response] = await Promise.all([
    page.waitForResponse(
      (res) => res.url().includes('/expenses/') && res.request().method() === 'PUT',
    ),
    page.getByRole('button', { name: /save/i }).click(),
  ])
  expect(response.status()).toBe(403)
})

// ---------------------------------------------------------------------------
// 10. Grace period: delete blocked after grace period expires
// ---------------------------------------------------------------------------

test('expense delete is blocked with 403 after the grace period has expired', async ({ page }) => {
  // Seed an expense in a month well beyond the grace period.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  const expense = await createExpenseViaApi(
    ctx,
    familyId,
    groceryCategoryId,
    1500,
    'Expired transport',
    toDateString(EXPIRED_MONTH),
  )
  await ctx.dispose()

  const expensesPage = new ExpensesPage(page)
  await expensesPage.goto()

  // Navigate back to the expired month.
  await goBackMonths(expensesPage, EXPIRED_MONTHS_BACK)
  await expect(expensesPage.monthDisplay).toContainText(toMonthLabel(EXPIRED_MONTH), {
    timeout: 5_000,
  })

  // The expense should be visible.
  await expect(page.getByText('Expired transport')).toBeVisible({ timeout: 10_000 })

  // Attempt delete — the API should return 403 (grace period expired).
  await expensesPage.deleteExpense(expense.id)
  await expect(expensesPage.dialogRoot).toBeVisible({ timeout: 5_000 })

  const [response] = await Promise.all([
    page.waitForResponse(
      (res) => res.url().includes('/expenses/') && res.request().method() === 'DELETE',
    ),
    page.getByTestId('delete-expense-confirm').click(),
  ])
  expect(response.status()).toBe(403)
})

// ---------------------------------------------------------------------------
// 11. Grace period: dashboard budget summary reports is_editable = false
//     for months past the grace period
// ---------------------------------------------------------------------------

test('budget summary API returns is_editable=false for months past the grace period', async ({
  page,
}) => {
  // Seed an expense in a month past the grace period.
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  await createExpenseViaApi(
    ctx,
    familyId,
    groceryCategoryId,
    1000,
    'Expired item',
    toDateString(EXPIRED_MONTH),
  )
  await ctx.dispose()

  // Intercept the budget summary API response and capture its body.
  let capturedSummary: Record<string, unknown> | null = null
  await page.route('**/budget/summary*', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    capturedSummary = body as Record<string, unknown>
    await route.fulfill({ response })
  })

  const dashboard = new DashboardPage(page)
  await dashboard.goto()

  // Navigate back to the expired month.
  await goBackMonths(dashboard, EXPIRED_MONTHS_BACK)

  // Wait until the budget summary for that month loads.
  await page.waitForResponse(
    (res) =>
      res.url().includes('/budget/summary') && res.url().includes(toYearMonth(EXPIRED_MONTH)),
  )

  // The budget summary for the expired month should report is_editable = false.
  expect(capturedSummary).not.toBeNull()
  expect((capturedSummary as Record<string, unknown>)['is_editable']).toBe(false)
})
