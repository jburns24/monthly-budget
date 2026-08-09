/**
 * Exploratory browser session: login via dev-auth, optionally seed demo data,
 * then open a headed Chromium at http://localhost:8080/.
 *
 * Usage (from e2e/): node scripts/exploratory.mjs [--seed]
 */
import { chromium, request } from 'playwright'

const APP_BASE = 'http://localhost:8080'
const TEST_USER = { email: 'usera@e2e-test.com', display_name: 'User A' }
const FAMILY_NAME = 'Exploratory Family'

/** Stable demo expenses for the current month (idempotent by description). */
const SEED_EXPENSES = [
  { description: '[seed] Groceries run', category: 'Groceries', amount_cents: 8743, day: 3 },
  { description: '[seed] Coffee shop', category: 'Dining', amount_cents: 650, day: 5 },
  { description: '[seed] Gas fill-up', category: 'Transport', amount_cents: 4520, day: 8 },
  { description: '[seed] Movie night', category: 'Entertainment', amount_cents: 2800, day: 12 },
  { description: '[seed] Electric bill', category: 'Bills', amount_cents: 12500, day: 1 },
  { description: '[seed] Misc household', category: 'Other', amount_cents: 1999, day: 15 },
]

function currentYearMonth() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function seedExpenseDate(day) {
  const now = new Date()
  const y = now.getFullYear()
  const m = now.getMonth()
  const lastDay = new Date(y, m + 1, 0).getDate()
  const d = Math.min(day, lastDay, now.getDate())
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}

async function assertOk(res, label) {
  if (!res.ok()) {
    const body = await res.text()
    throw new Error(`${label} failed: ${res.status()} ${body}`)
  }
}

async function seedDemoData(api) {
  const meRes = await api.get('/api/me')
  await assertOk(meRes, 'GET /api/me')
  const me = await meRes.json()

  let familyId = me.family?.id ?? null
  if (!familyId) {
    console.log(`==> Creating family "${FAMILY_NAME}"`)
    const famRes = await api.post('/api/families', {
      data: { name: FAMILY_NAME, timezone: 'America/New_York' },
    })
    await assertOk(famRes, 'POST /api/families')
    const family = await famRes.json()
    familyId = family.id
  } else {
    console.log(`==> Using existing family ${familyId}`)
  }

  console.log('==> Seeding default categories (idempotent)')
  const seedRes = await api.post(`/api/families/${familyId}/categories/seed`)
  await assertOk(seedRes, 'POST categories/seed')
  const seedBody = await seedRes.json()
  console.log(`    ${seedBody.message}`)

  const catsRes = await api.get(`/api/families/${familyId}/categories`)
  await assertOk(catsRes, 'GET categories')
  /** @type {{ id: string, name: string }[]} */
  const categories = await catsRes.json()
  const byName = Object.fromEntries(categories.map((c) => [c.name, c.id]))

  const yearMonth = currentYearMonth()
  const listRes = await api.get(`/api/families/${familyId}/expenses?year_month=${yearMonth}&per_page=200`)
  await assertOk(listRes, 'GET expenses')
  const listBody = await listRes.json()
  const existing = new Set(
    (listBody.expenses ?? []).map((e) => e.description).filter(Boolean),
  )

  let created = 0
  let skipped = 0
  for (const item of SEED_EXPENSES) {
    if (existing.has(item.description)) {
      skipped += 1
      continue
    }
    const categoryId = byName[item.category]
    if (!categoryId) {
      throw new Error(`Seed category missing: ${item.category}`)
    }
    const createRes = await api.post(`/api/families/${familyId}/expenses`, {
      data: {
        amount_cents: item.amount_cents,
        description: item.description,
        category_id: categoryId,
        expense_date: seedExpenseDate(item.day),
      },
    })
    await assertOk(createRes, `POST expense ${item.description}`)
    created += 1
  }
  console.log(`==> Expenses for ${yearMonth}: created=${created} skipped=${skipped}`)
}

async function main() {
  const seed = process.argv.includes('--seed')

  const api = await request.newContext({
    baseURL: APP_BASE,
    extraHTTPHeaders: { 'Content-Type': 'application/json' },
  })

  try {
    console.log(`==> Dev-login as ${TEST_USER.email}`)
    const loginRes = await api.post('/api/auth/dev-login', {
      data: TEST_USER,
    })
    await assertOk(loginRes, 'POST /api/auth/dev-login')
    const loginBody = await loginRes.json()
    console.log(`    user_id=${loginBody.user_id} is_new_user=${loginBody.is_new_user}`)

    if (seed) {
      await seedDemoData(api)
    }

    const storageState = await api.storageState()

    console.log(`==> Opening headed browser at ${APP_BASE}/`)
    const browser = await chromium.launch({
      headless: false,
      args: ['--start-maximized'],
    })
    const context = await browser.newContext({
      storageState,
      viewport: null,
    })
    const page = await context.newPage()
    await page.goto(`${APP_BASE}/`, { waitUntil: 'domcontentloaded' })
    await page.bringToFront()

    // Playwright's Chromium often opens behind the IDE on macOS — force focus.
    if (process.platform === 'darwin') {
      const { execFile } = await import('node:child_process')
      const { promisify } = await import('node:util')
      const execFileAsync = promisify(execFile)
      await execFileAsync('osascript', [
        '-e',
        'tell application "Google Chrome for Testing" to activate',
      ]).catch(() => {})
    }

    console.log('==> Browser open. Close the window when finished.')
    await new Promise((resolve) => {
      browser.on('disconnected', resolve)
    })
  } finally {
    await api.dispose()
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
