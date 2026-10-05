/**
 * E2E tests for editing recurring rules from the Recurring page.
 *
 * Edits only affect future entries; moving the next date, changing the frequency
 * and extending an ended rule each have their own guard rails.
 */
import { test, expect, request as playwrightRequest } from '@playwright/test'
import {
  resetTestData,
  createFamilyViaApi,
  createCategoryViaApi,
  createRecurringViaApi,
} from '../fixtures/test-data'

const API_BASE = 'http://localhost:8000'

function isoDaysFromToday(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

let familyId: string
let categoryId: string
let ruleId: string

test.beforeEach(async () => {
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await resetTestData(ctx)
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  const family = await createFamilyViaApi(ctx, 'Recurring Edit Family')
  familyId = family.id
  categoryId = (await createCategoryViaApi(ctx, familyId, 'Housing', '🏠')).id
  const rule = await createRecurringViaApi(ctx, familyId, {
    amount_cents: 150000,
    category_id: categoryId,
    frequency: 'monthly',
    start_date: isoDaysFromToday(10),
    description: 'Rent',
  })
  ruleId = rule.id
  await ctx.storageState({ path: 'playwright/.auth/user.json' })
  await ctx.dispose()
})

test('editing amount, description and frequency updates the row', async ({ page }) => {
  await page.goto('/recurring')
  await page.getByTestId(`recurring-edit-${ruleId}`).click()

  await expect(page.getByTestId('edit-recurring-amount')).toHaveValue('1500')
  await page.getByTestId('edit-recurring-amount').fill('1600')
  await page.getByTestId('edit-recurring-description').fill('Rent (new lease)')
  await page.getByTestId('edit-recurring-frequency').selectOption('weekly')
  await expect(page.getByTestId('edit-recurring-frequency-hint')).toBeVisible()
  await page.getByTestId('edit-recurring-save').click()

  const row = page.getByTestId(`recurring-row-${ruleId}`)
  await expect(row).toContainText('Rent (new lease)')
  await expect(row).toContainText('−$1,600')
  await expect(row).toContainText('Weekly')
})

test('moving the next date works for a future date and is blocked for today or earlier', async ({
  page,
}) => {
  await page.goto('/recurring')
  await page.getByTestId(`recurring-edit-${ruleId}`).click()

  await page.getByTestId('edit-recurring-next').fill(isoDaysFromToday(0))
  await expect(page.getByTestId('edit-recurring-next-hint')).toBeVisible()
  await expect(page.getByTestId('edit-recurring-save')).toBeDisabled()

  const target = isoDaysFromToday(25)
  await page.getByTestId('edit-recurring-next').fill(target)
  await expect(page.getByTestId('edit-recurring-next-hint')).toHaveCount(0)
  await page.getByTestId('edit-recurring-save').click()

  await expect(page.getByTestId('edit-recurring-save')).toHaveCount(0)
  const [y, m, d] = target.split('-').map(Number)
  const label = new Date(y, m - 1, d).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    ...(y !== new Date().getFullYear() ? { year: 'numeric' } : {}),
  })
  await expect(page.getByTestId(`recurring-row-${ruleId}`)).toContainText(`Next ${label}`)
})

test('an end date before the next date is rejected in the form', async ({ page }) => {
  await page.goto('/recurring')
  await page.getByTestId(`recurring-edit-${ruleId}`).click()
  await page.getByTestId('edit-recurring-end').fill(isoDaysFromToday(2))
  await expect(page.getByTestId('edit-recurring-end-hint')).toBeVisible()
  await expect(page.getByTestId('edit-recurring-save')).toBeDisabled()
})

test('an ended rule shows Ended and comes back when the end date is extended', async ({ page }) => {
  const ctx = await playwrightRequest.newContext({
    baseURL: API_BASE,
    storageState: 'playwright/.auth/user.json',
  })
  // Weekly rule that finished last week: all occurrences already generated, so it ends.
  const ended = await createRecurringViaApi(ctx, familyId, {
    amount_cents: 500,
    category_id: categoryId,
    frequency: 'weekly',
    start_date: isoDaysFromToday(-14),
    end_date: isoDaysFromToday(-7),
    description: 'Old gym',
  })
  await ctx.dispose()

  await page.goto('/recurring')
  const row = page.getByTestId(`recurring-row-${ended.id}`)
  await expect(row).toContainText('Ended')
  await page.getByTestId(`recurring-edit-${ended.id}`).click()
  await expect(page.getByTestId('edit-recurring-toggle')).toHaveCount(0)
  await page.getByTestId('edit-recurring-end').fill(isoDaysFromToday(60))
  await page.getByTestId('edit-recurring-save').click()

  await expect(row).not.toContainText('Ended')
  await expect(row).not.toContainText('Paused')
  await page.getByTestId(`recurring-edit-${ended.id}`).click()
  await expect(page.getByTestId('edit-recurring-toggle')).toHaveText('Pause')
})

test('pause and resume from the edit dialog, and paused rules sort last', async ({ page }) => {
  const ctx = await playwrightRequest.newContext({
    baseURL: API_BASE,
    storageState: 'playwright/.auth/user.json',
  })
  const second = await createRecurringViaApi(ctx, familyId, {
    amount_cents: 900,
    category_id: categoryId,
    frequency: 'monthly',
    start_date: isoDaysFromToday(20),
    description: 'Streaming',
  })
  await ctx.dispose()

  await page.goto('/recurring')
  await page.getByTestId(`recurring-edit-${ruleId}`).click()
  await page.getByTestId('edit-recurring-toggle').click()

  await expect(page.getByTestId(`recurring-meta-${ruleId}`)).toContainText('Paused')
  const rows = page.locator('[data-testid^="recurring-row-"]')
  await expect(rows.last()).toHaveAttribute('data-testid', `recurring-row-${ruleId}`)
  await expect(rows.first()).toHaveAttribute('data-testid', `recurring-row-${second.id}`)

  await page.getByTestId(`recurring-edit-${ruleId}`).click()
  await expect(page.getByTestId('edit-recurring-toggle')).toHaveText('Resume')
  await page.getByTestId('edit-recurring-toggle').click()
  await expect(page.getByTestId(`recurring-meta-${ruleId}`)).not.toContainText('Paused')
})

test('deleting needs an inline confirmation and removes the row', async ({ page }) => {
  await page.goto('/recurring')
  await page.getByTestId(`recurring-edit-${ruleId}`).click()
  await page.getByTestId('edit-recurring-delete').click()
  await page.getByText('Keep').click()
  await expect(page.getByTestId(`recurring-row-${ruleId}`)).toBeVisible()

  await page.getByTestId('edit-recurring-delete').click()
  await page.getByTestId('edit-recurring-delete-confirm').click()
  await expect(page.getByTestId(`recurring-row-${ruleId}`)).toHaveCount(0)
})

test('rows stay readable on a 320px screen with a very long description', async ({ page }) => {
  const ctx = await playwrightRequest.newContext({
    baseURL: API_BASE,
    storageState: 'playwright/.auth/user.json',
  })
  await createRecurringViaApi(ctx, familyId, {
    amount_cents: 123456789,
    category_id: categoryId,
    frequency: 'biweekly',
    start_date: isoDaysFromToday(5),
    description: 'An extremely long description that should be truncated rather than wrap '.repeat(
      3
    ),
  })
  await ctx.dispose()

  await page.setViewportSize({ width: 320, height: 640 })
  await page.goto('/recurring')
  await expect(page.getByTestId('recurring-list')).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth
  )
  expect(overflow).toBeLessThanOrEqual(0)
  const box = await page.getByTestId(`recurring-row-${ruleId}`).boundingBox()
  expect(box!.height).toBeLessThan(80)
})
