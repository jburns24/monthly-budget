/**
 * Auth fixture that provides a second authenticated API context for multi-user
 * scenarios (e.g. the invite flow where User A invites User B).
 */
import { test as base, APIRequestContext } from '@playwright/test'

const API_BASE = 'http://localhost:8000'

export type AuthFixtures = {
  /** An APIRequestContext authenticated as User B (invitee). */
  userBContext: APIRequestContext
}

export const test = base.extend<AuthFixtures>({
  userBContext: async ({ playwright }, use) => {
    const ctx = await playwright.request.newContext({ baseURL: API_BASE })
    await ctx.post('/api/auth/dev-login', {
      data: { email: 'userb@e2e-test.com', display_name: 'User B' },
    })
    await use(ctx)
    await ctx.dispose()
  },
})

export { expect } from '@playwright/test'
