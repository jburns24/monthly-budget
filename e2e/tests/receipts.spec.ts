/**
 * E2E tests for the receipt scanning feature.
 *
 * Requires backend running with ANTHROPIC_MOCK=true. That now comes from
 * manifests/overlays/dev/config/app-config.env, which kustomize renders into
 * the app-config ConfigMap that the backend Deployment pulls in via envFrom --
 * it is no longer set in the Tiltfile.
 * Uses POST /api/dev/mock-claude to control deterministic Claude responses.
 *
 * Scenarios:
 *   (a) happy-path: success → expense appears in list
 *   (b) non_receipt: 422 → error toast shown
 *   (c) low_confidence: 201 + needs_edit → "Needs review" badge shown
 *   (d) api_error: 503 → error toast shown
 *   (e) multi-user: User A uploads → User B sees expense via API
 */
import * as path from 'path'
import { test, expect } from '../fixtures/auth'
import { request as playwrightRequest } from '@playwright/test'
import {
  resetTestData,
  createFamilyViaApi,
  createCategoryViaApi,
  sendInviteViaApi,
  setMockScenario,
} from '../fixtures/test-data'

const API_BASE = 'http://localhost:8000'
const SAMPLE_RECEIPT = path.join(__dirname, '../fixtures/sample-receipt.jpg')

let familyId: string

test.beforeEach(async () => {
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await resetTestData(ctx)
  await ctx.post('/api/auth/dev-login', { data: { email: 'usera@e2e-test.com', display_name: 'User A' } })
  const family = await createFamilyViaApi(ctx, 'Receipt Test Family')
  familyId = family.id
  await createCategoryViaApi(ctx, familyId, 'Groceries', '🛒')
  await ctx.storageState({ path: 'playwright/.auth/user.json' })
  await ctx.dispose()
})

// ---------------------------------------------------------------------------
// (a) Happy path: success scenario → expense appears in list
// ---------------------------------------------------------------------------

test('receipt upload success — expense created and shown in reviewing state', async ({ page, request }) => {
  await setMockScenario(request, 'success')

  await page.goto('/expenses')
  await expect(page.getByTestId('fab-scan-receipt')).toBeVisible({ timeout: 10_000 })
  await page.getByTestId('fab-scan-receipt').click()

  await expect(page.getByTestId('receipt-capture-dialog')).toBeVisible({ timeout: 5_000 })
  await expect(page.getByTestId('receipt-file-input')).toBeAttached()

  await page.getByTestId('receipt-file-input').setInputFiles(SAMPLE_RECEIPT)
  await expect(page.getByTestId('receipt-upload-btn')).toBeVisible({ timeout: 5_000 })
  await page.getByTestId('receipt-upload-btn').click()

  // Should transition through uploading → reviewing
  await expect(page.getByTestId('receipt-reviewing')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId('receipt-merchant')).toContainText('Test Market')
  await expect(page.getByTestId('receipt-amount')).toContainText('$42.50')

  // Confirm the review
  await page.getByTestId('receipt-confirm-btn').click()
  await expect(page.getByTestId('receipt-done')).toBeVisible({ timeout: 5_000 })
})

// ---------------------------------------------------------------------------
// (b) non_receipt scenario → 422 error toast
// ---------------------------------------------------------------------------

test('receipt upload non_receipt — error toast shown', async ({ page, request }) => {
  await setMockScenario(request, 'non_receipt')

  await page.goto('/expenses')
  await expect(page.getByTestId('fab-scan-receipt')).toBeVisible({ timeout: 10_000 })
  await page.getByTestId('fab-scan-receipt').click()

  await expect(page.getByTestId('receipt-capture-dialog')).toBeVisible({ timeout: 5_000 })
  await page.getByTestId('receipt-file-input').setInputFiles(SAMPLE_RECEIPT)
  await expect(page.getByTestId('receipt-upload-btn')).toBeVisible({ timeout: 5_000 })
  await page.getByTestId('receipt-upload-btn').click()

  // Expect error toast describing non-receipt image
  await expect(page.getByText("That doesn't look like a receipt")).toBeVisible({ timeout: 15_000 })
  // Dialog should return to preview phase (back button visible)
  await expect(page.getByTestId('receipt-back-btn')).toBeVisible({ timeout: 5_000 })
})

// ---------------------------------------------------------------------------
// (c) low_confidence scenario → "Needs review" badge shown
// ---------------------------------------------------------------------------

test('receipt upload low_confidence — Needs review badge shown', async ({ page, request }) => {
  await setMockScenario(request, 'low_confidence')

  await page.goto('/expenses')
  await expect(page.getByTestId('fab-scan-receipt')).toBeVisible({ timeout: 10_000 })
  await page.getByTestId('fab-scan-receipt').click()

  await expect(page.getByTestId('receipt-capture-dialog')).toBeVisible({ timeout: 5_000 })
  await page.getByTestId('receipt-file-input').setInputFiles(SAMPLE_RECEIPT)
  await expect(page.getByTestId('receipt-upload-btn')).toBeVisible({ timeout: 5_000 })
  await page.getByTestId('receipt-upload-btn').click()

  await expect(page.getByTestId('receipt-reviewing')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId('receipt-needs-review-badge')).toBeVisible({ timeout: 5_000 })
  await expect(page.getByTestId('receipt-needs-review-badge')).toContainText('Needs review')
})

// ---------------------------------------------------------------------------
// (d) api_error scenario → 503 error toast
// ---------------------------------------------------------------------------

test('receipt upload api_error — service unavailable toast shown', async ({ page, request }) => {
  await setMockScenario(request, 'api_error')

  await page.goto('/expenses')
  await expect(page.getByTestId('fab-scan-receipt')).toBeVisible({ timeout: 10_000 })
  await page.getByTestId('fab-scan-receipt').click()

  await expect(page.getByTestId('receipt-capture-dialog')).toBeVisible({ timeout: 5_000 })
  await page.getByTestId('receipt-file-input').setInputFiles(SAMPLE_RECEIPT)
  await expect(page.getByTestId('receipt-upload-btn')).toBeVisible({ timeout: 5_000 })
  await page.getByTestId('receipt-upload-btn').click()

  // Expect error toast describing service unavailability
  await expect(page.getByText('Receipt service unavailable')).toBeVisible({ timeout: 15_000 })
  // Dialog should return to preview phase
  await expect(page.getByTestId('receipt-back-btn')).toBeVisible({ timeout: 5_000 })
})

// ---------------------------------------------------------------------------
// (e) Multi-user: User A uploads → User B sees expense via API
// ---------------------------------------------------------------------------

test('multi-user: User A uploads receipt, User B sees the expense', async ({ userBContext, request }) => {
  await setMockScenario(request, 'success')

  // User B joins User A's family
  const adminCtx = await playwrightRequest.newContext({ baseURL: API_BASE })
  await adminCtx.post('/api/auth/dev-login', { data: { email: 'usera@e2e-test.com', display_name: 'User A' } })

  // User B is created via the fixture — send them an invite
  await sendInviteViaApi(adminCtx, familyId, 'userb@e2e-test.com')

  // User B accepts the invite
  const invitesRes = await userBContext.get(`${API_BASE}/api/invites`)
  const invites = (await invitesRes.json()) as Array<{ id: string }>
  expect(invites.length).toBeGreaterThan(0)
  await userBContext.post(`${API_BASE}/api/invites/${invites[0].id}/respond`, {
    data: { action: 'accept' },
  })

  // User A uploads a receipt via API
  const receiptPath = SAMPLE_RECEIPT
  const { createReadStream } = await import('fs')
  const fs = await import('fs')
  const imageBytes = fs.readFileSync(receiptPath)

  const uploadRes = await adminCtx.post(`${API_BASE}/api/families/${familyId}/receipts`, {
    multipart: {
      file: {
        name: 'sample-receipt.jpg',
        mimeType: 'image/jpeg',
        buffer: imageBytes,
      },
    },
  })
  expect(uploadRes.ok()).toBeTruthy()
  const uploadBody = (await uploadRes.json()) as { expense_id: string | null }
  expect(uploadBody.expense_id).toBeTruthy()

  // User B fetches expenses for the family. `year_month` is a required query
  // param on GET /api/families/{id}/expenses — derive it from today so the test
  // keeps working as the calendar advances.
  const now = new Date()
  const yearMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  const expensesRes = await userBContext.get(
    `${API_BASE}/api/families/${familyId}/expenses?year_month=${yearMonth}`,
  )
  expect(expensesRes.ok()).toBeTruthy()
  const body = (await expensesRes.json()) as {
    expenses: Array<{ id: string; description: string }>
  }

  // The expense created from the receipt should be visible to User B
  expect(body.expenses.some((e) => e.id === uploadBody.expense_id)).toBeTruthy()

  await adminCtx.dispose()
})
