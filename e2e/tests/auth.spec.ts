/**
 * E2E tests for the authentication flow.
 *
 * These tests run in the "chromium" project which inherits the authenticated
 * storageState saved by auth.setup.ts.  Tests that need an unauthenticated
 * browser use a fresh context with no storageState.
 */
import { test, expect, Browser } from '@playwright/test'
import { LoginPage } from '../pages/login.page'

// ---------------------------------------------------------------------------
// Unauthenticated tests — use a fresh, cookie-less browser context
// ---------------------------------------------------------------------------

test.describe('unauthenticated', () => {
  let browser: Browser

  test('redirect to /login when not authenticated', async ({ browser: b }) => {
    browser = b
    const ctx = await b.newContext({ storageState: undefined })
    const page = await ctx.newPage()

    await page.goto('http://localhost:5173/')
    await expect(page).toHaveURL(/\/login/)

    await ctx.close()
  })

  test('login page renders Google sign-in button', async ({ browser: b }) => {
    const ctx = await b.newContext({ storageState: undefined })
    const page = await ctx.newPage()
    const loginPage = new LoginPage(page)

    await loginPage.goto()
    await expect(loginPage.googleSignInButton).toBeVisible()

    await ctx.close()
  })
})

// ---------------------------------------------------------------------------
// Authenticated tests — use the storageState from auth.setup.ts
// ---------------------------------------------------------------------------

test.describe('authenticated', () => {
  test('authenticated user can access home page', async ({ page }) => {
    await page.goto('/')
    // Should NOT be redirected to /login
    await expect(page).not.toHaveURL(/\/login/)
  })

  test('logout clears session and redirects to login', async ({ page }) => {
    await page.goto('/')

    // Click the logout button in the header (button text is "Sign out")
    await page.getByRole('button', { name: /sign out/i }).click()

    // Should land on the login page
    await expect(page).toHaveURL(/\/login/)

    // Protected routes should now redirect back to login
    await page.goto('/family')
    await expect(page).toHaveURL(/\/login/)
  })
})
