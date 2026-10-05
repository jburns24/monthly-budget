/**
 * E2E tests for the "Repeat" checkbox in the expense create/edit dialogs.
 *
 * Checking "Repeat" reveals the recurring fields; saving creates a recurring
 * rule that the backend reconciles immediately (entries dated today or earlier
 * appear straight away).
 */
import { test, expect, request as playwrightRequest } from '@playwright/test'
import { ExpensesPage } from '../pages/expenses.page'
import {
  resetTestData,
  createFamilyViaApi,
  createCategoryViaApi,
  createExpenseViaApi,
} from '../fixtures/test-data'

const API_BASE = 'http://localhost:8000'

let familyId: string
let groceryCategoryId: string

/** First day of the current month — always on or before today, so it is due immediately. */
const CURRENT_DATE = (() => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
})()

test.beforeEach(async () => {
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await resetTestData(ctx)
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  const family = await createFamilyViaApi(ctx, 'Recurring Test Family')
  familyId = family.id
  const grocery = await createCategoryViaApi(ctx, familyId, 'Groceries', '🛒')
  groceryCategoryId = grocery.id
  await ctx.storageState({ path: 'playwright/.auth/user.json' })
  await ctx.dispose()
})

test('repeat checkbox reveals and hides the recurring fields', async ({ page }) => {
  const expensesPage = new ExpensesPage(page)
  await expensesPage.goto()
  await expensesPage.openCreateDialog()

  await expect(expensesPage.repeatCheckbox).not.toBeChecked()
  await expect(expensesPage.repeatFrequencySelect).toHaveCount(0)

  await expensesPage.repeatCheckbox.check()
  await expect(expensesPage.repeatFrequencySelect).toBeVisible()
  await expect(expensesPage.repeatEndInput).toBeVisible()

  await expensesPage.repeatCheckbox.uncheck()
  await expect(expensesPage.repeatFrequencySelect).toHaveCount(0)
})

test('creating a repeating expense adds the entry now and a rule on the Recurring page', async ({
  page,
}) => {
  const expensesPage = new ExpensesPage(page)
  await expensesPage.goto()
  await expensesPage.openCreateDialog()

  await expensesPage.repeatCheckbox.check()
  await expensesPage.repeatFrequencySelect.selectOption('monthly')

  const [response] = await Promise.all([
    page.waitForResponse(
      (res) => res.url().includes('/recurring-expenses') && res.request().method() === 'POST',
    ),
    expensesPage.fillExpenseForm({
      amount: '1200',
      description: 'Rent',
      categoryId: groceryCategoryId,
      date: CURRENT_DATE,
    }),
  ])
  expect(response.status()).toBe(201)

  // The first occurrence is created immediately and flagged as recurring.
  await expect(page.getByText('Rent')).toBeVisible({ timeout: 10_000 })
  await expect(page.locator('[data-testid^="expense-recurring-"]')).toHaveCount(1)

  // The rule shows up on the Recurring page.
  await page.goto('/recurring')
  await expect(page.getByTestId('recurring-list')).toContainText('Rent')

  // Editing the generated entry shows the checkbox locked on.
  await expensesPage.goto()
  await expensesPage.editButtons.first().click()
  await expect(expensesPage.repeatCheckbox).toBeChecked()
  await expect(expensesPage.repeatCheckbox).toBeDisabled()
  await expect(page.getByTestId('repeat-locked-hint')).toBeVisible()
})

test('editing a one-off expense and checking Repeat creates a rule without duplicating it', async ({
  page,
}) => {
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  const expense = await createExpenseViaApi(
    ctx,
    familyId,
    groceryCategoryId,
    5000,
    'Gym',
    CURRENT_DATE,
  )
  await ctx.dispose()

  const expensesPage = new ExpensesPage(page)
  await expensesPage.goto()
  await expect(page.getByText('Gym')).toBeVisible({ timeout: 10_000 })

  await expensesPage.editExpense(expense.id)
  await expect(expensesPage.repeatCheckbox).not.toBeChecked()
  await expensesPage.repeatCheckbox.check()
  await expensesPage.repeatFrequencySelect.selectOption('weekly')

  const [response] = await Promise.all([
    page.waitForResponse(
      (res) => res.url().includes('/recurring-expenses') && res.request().method() === 'POST',
    ),
    expensesPage.editSaveButton.click(),
  ])
  expect(response.status()).toBe(201)

  // Rule exists on the Recurring page.
  await page.goto('/recurring')
  await expect(page.getByTestId('recurring-list')).toContainText('Gym')

  // The original entry is not duplicated by the new rule's first reconcile
  // (the rule starts at the next occurrence, a week later).
  await expensesPage.goto()
  await expect(expensesPage.expenseCard(expense.id)).toHaveCount(1)
})
