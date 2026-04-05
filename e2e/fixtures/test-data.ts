/**
 * Test-data factory helpers — create users, families, and invites directly via
 * the backend API so tests can seed state without going through the UI.
 */
import { APIRequestContext } from '@playwright/test'

const API_BASE = 'http://localhost:8000'

export interface CreatedUser {
  user_id: string
  email: string
  is_new_user: boolean
}

/**
 * Create (or retrieve) a user via the dev-login endpoint, returning an
 * APIRequestContext that is authenticated as that user.
 */
export async function loginAs(
  playwright: { request: { newContext: (opts: object) => Promise<APIRequestContext> } },
  email: string,
  displayName: string,
): Promise<{ ctx: APIRequestContext; user: CreatedUser }> {
  const ctx = await playwright.request.newContext({ baseURL: API_BASE })
  const res = await ctx.post('/api/auth/dev-login', {
    data: { email, display_name: displayName },
  })
  const user = (await res.json()) as CreatedUser
  return { ctx, user }
}

/**
 * Reset all test data (truncates invites, family_members, families, users,
 * refresh_token_blacklist).  Call in beforeAll / beforeEach.
 */
export async function resetTestData(request: APIRequestContext): Promise<void> {
  const res = await request.post(`${API_BASE}/api/test/reset`)
  if (!res.ok()) {
    throw new Error(`test/reset failed: ${res.status()} ${await res.text()}`)
  }
}

/**
 * Create a family for the authenticated user represented by *ctx*.
 * Returns the created family object.
 */
export async function createFamilyViaApi(
  ctx: APIRequestContext,
  name: string,
  timezone = 'America/New_York',
): Promise<{ id: string; name: string }> {
  const res = await ctx.post(`${API_BASE}/api/families`, {
    data: { name, timezone },
  })
  if (!res.ok()) {
    throw new Error(`createFamily failed: ${res.status()} ${await res.text()}`)
  }
  return res.json() as Promise<{ id: string; name: string }>
}

/**
 * Create a category for the given family via the backend API.
 * Returns the created category object ({ id, name }).
 */
export async function createCategoryViaApi(
  ctx: APIRequestContext,
  familyId: string,
  name: string,
  icon?: string,
): Promise<{ id: string; name: string }> {
  const res = await ctx.post(`${API_BASE}/api/families/${familyId}/categories`, {
    data: { name, ...(icon !== undefined ? { icon } : {}) },
  })
  if (!res.ok()) {
    throw new Error(`createCategory failed: ${res.status()} ${await res.text()}`)
  }
  return res.json() as Promise<{ id: string; name: string }>
}

/**
 * Send an invite from the authenticated context *ctx* for *familyId* to
 * *inviteeEmail*.  Returns the invite object.
 */
export async function sendInviteViaApi(
  ctx: APIRequestContext,
  familyId: string,
  inviteeEmail: string,
): Promise<{ id: string }> {
  const res = await ctx.post(`${API_BASE}/api/families/${familyId}/invites`, {
    data: { email: inviteeEmail },
  })
  if (!res.ok()) {
    throw new Error(`sendInvite failed: ${res.status()} ${await res.text()}`)
  }
  return res.json() as Promise<{ id: string }>
}
