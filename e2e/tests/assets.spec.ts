/**
 * E2E test for the assets feature: an admin adds a house with a loan, links an expense to it
 * as an improvement, then checks the asset's detail page.
 *
 * The house value comes from the FHFA index when the backend has it and falls back to the
 * purchase price otherwise, so only the shape of the equity figure is asserted, not its value.
 */
import { test, expect, request as playwrightRequest } from '@playwright/test'
import { AssetsPage, AssetDetailPage } from '../pages/assets.page'
import { ExpensesPage } from '../pages/expenses.page'
import { resetTestData, createFamilyViaApi, createCategoryViaApi } from '../fixtures/test-data'

const API_BASE = 'http://localhost:8000'

/** Calendar date parts in the family's timezone (the backend's "today"), not the runner's. */
const FAMILY_TIMEZONE = 'America/New_York'
const [todayYear, todayMonth, todayDay] = new Intl.DateTimeFormat('en-CA', {
  timeZone: FAMILY_TIMEZONE,
})
  .format(new Date())
  .split('-')
  .map(Number)

function isoDate(year: number, month: number, day: number): string {
  // Date.UTC normalises an out-of-range month (e.g. 13) into the next year.
  const d = new Date(Date.UTC(year, month - 1, day))
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
}

/** First of the month, two years back, so the loan has a real balance and some history. */
const PURCHASE_DATE = isoDate(todayYear - 2, todayMonth, 1)
const FIRST_PAYMENT_DATE = isoDate(todayYear - 2, todayMonth + 1, 1)
const TODAY = isoDate(todayYear, todayMonth, todayDay)

let categoryId: string

test.beforeEach(async () => {
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await resetTestData(ctx)
  await ctx.post('/api/auth/dev-login', {
    data: { email: 'usera@e2e-test.com', display_name: 'User A' },
  })
  // The family's creator is its admin.
  const family = await createFamilyViaApi(ctx, 'Asset Family')
  categoryId = (await createCategoryViaApi(ctx, family.id, 'Housing', '🏠')).id
  await ctx.storageState({ path: 'playwright/.auth/user.json' })
  await ctx.dispose()
})

test('admin adds a house with a loan, links an improvement and sees it on the detail page', async ({
  page,
}) => {
  const assets = new AssetsPage(page)
  const expenses = new ExpensesPage(page)
  const detail = new AssetDetailPage(page)

  await assets.goto()
  await assets.openCreateDialog()
  await assets.createHouse({
    name: 'Maple Street',
    state: 'NC',
    zip: '27601',
    purchaseDate: PURCHASE_DATE,
    price: '400000',
    downPayment: '80000',
    loan: { amount: '320000', ratePct: '6.25', firstPaymentDate: FIRST_PAYMENT_DATE },
  })
  await expect(assets.cardNamed('Maple Street')).toBeVisible()

  await expenses.goto()
  await expenses.openCreateDialog()
  await expenses.fillExpenseForm({
    amount: '8500',
    description: 'New water heater',
    categoryId,
    date: TODAY,
    asset: { name: 'Maple Street', role: 'improvement' },
  })
  // The dialog closes once the expense is saved.
  await expect(expenses.submitButton).toHaveCount(0)

  await assets.goto()
  await assets.cardNamed('Maple Street').click()

  await expect(detail.name).toHaveText('Maple Street')
  await expect(detail.equity).toHaveText(/^−?\$[\d,]+$/)
  await expect(detail.loanBalance).toHaveText(/^\$[\d,]+$/)
  await expect(detail.equityBuilding).toContainText('Improvements')
  await expect(detail.equityBuilding).toContainText('$8,500')
  await expect(detail.linkedExpenses).toContainText('New water heater')
  await expect(detail.linkedExpenses).toContainText('Improvement')
})
