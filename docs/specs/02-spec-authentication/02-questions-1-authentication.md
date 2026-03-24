# 02 Questions Round 1 - Authentication (Google OAuth + JWT)

The PRD (§9) defines the auth system: Google OAuth 2.0 with PKCE, JWT access/refresh tokens in HttpOnly cookies, and a `users` table. Epic 02 builds this as the foundation for all subsequent epics.

Please answer each question below (select one or more options, or add your own notes). Feel free to add additional context under any question.

---

## 1. OAuth Flow Initiation

The PRD shows the frontend generating PKCE `code_verifier`/`code_challenge` client-side, then the backend exchanging the auth code. How should login be initiated?

- [x] (A) **Frontend-initiated PKCE** — React generates the PKCE pair, redirects to Google, receives callback, then POSTs `auth_code + code_verifier` to the backend (matches PRD §9.1 exactly)
- [ ] (B) **Backend-initiated flow** — `GET /api/auth/google/login` redirects to Google (backend generates state + PKCE), callback hits backend directly. Simpler but less SPA-friendly
- [ ] (C) **Hybrid** — Backend generates the auth URL (including PKCE), returns it to the frontend, frontend redirects. Callback hits backend. Balances security and simplicity
- [ ] (D) Other (describe)

## 2. Token Storage & Delivery

The PRD specifies HttpOnly Secure SameSite=Strict cookies for both access and refresh tokens. Are you aligned with this, or do you want a different approach for local development?

- [x] (A) **HttpOnly cookies for everything** — exactly as PRD specifies. For local dev, use `Secure=False` when `ENVIRONMENT=development`
- [ ] (B) **Access token in memory (React state), refresh token in HttpOnly cookie** — more common SPA pattern, avoids CSRF concerns on API calls
- [ ] (C) **HttpOnly cookies with CSRF double-submit token** — cookies for both tokens + a CSRF token in a non-HttpOnly cookie that must be echoed in a header
- [ ] (D) Other (describe)

## 3. User Table Scope

The PRD's `users` table includes `google_id`, `email`, `display_name`, `avatar_url`, `timezone`. Should this epic create:

- [x] (A) **Only the `users` table + `refresh_token_blacklist` table** — families and family_members belong to Epic 03
- [ ] (B) **`users` + `refresh_token_blacklist` + skeleton `families`/`family_members`** — so the `/me` endpoint can return family memberships (even if empty)
- [ ] (C) **Just `users`** — no blacklist table; use Redis for token blacklisting instead of a DB table
- [ ] (D) Other (describe)

## 4. Post-Login Redirect

After a user successfully authenticates, where should they land?

- [ ] (A) **Always redirect to `/`** (homepage/dashboard) — let the frontend figure out what to show based on whether they have a family
- [ ] (B) **Backend returns JSON with user info + redirect hint** — frontend decides where to route (e.g., `/onboarding` for new users, `/dashboard` for returning users)
- [x] (C) **Redirect to `/` with a `?new=true` query param** for first-time users so the frontend can show a welcome state
- [ ] (D) Other (describe)

## 5. Refresh Token Strategy

The PRD says 7-day refresh tokens with blacklisting on logout. Additional questions:

- [x] (A) **DB blacklist table** (`refresh_token_blacklist`) — as specified in PRD §10. Simple, durable, works across restarts
- [ ] (B) **Redis-based blacklist** — faster lookups, auto-expiry via TTL. Less durable but the tokens expire anyway
- [ ] (C) **Token rotation** — each refresh issues a new refresh token and blacklists the old one. Detects token theft
- [ ] (D) Other (describe)

## 6. Frontend Auth State Management

How should the React app manage authentication state?

- [x] (A) **React Query + `/api/me` endpoint** — on app load, call `/me`. If 401, user is not authenticated. Use React Query's cache for user data
- [ ] (B) **React Context with auth provider** — dedicated AuthContext wrapping the app, manages login/logout/refresh state
- [ ] (C) **Both** — AuthContext for login/logout actions, React Query for fetching/caching user data from `/me`
- [ ] (D) Other (describe)

## 7. Protected Routes

How should unauthenticated users be handled on protected pages?

- [x] (A) **Redirect to login page** — a dedicated `/login` route with the Google Sign-In button
- [ ] (B) **Show login modal/overlay** — no dedicated login page, just a modal that appears over the current page
- [ ] (C) **Landing page with login** — a public landing/marketing page at `/` with a login button. Authenticated users see the app
- [ ] (D) Other (describe)

## 8. Testing Approach

The epic breakdown says full testing pyramid per epic. How should we handle testing auth specifically?

- [x] (A) **Mock Google OAuth in tests** — use httpx mocking to simulate Google's token exchange. Real JWT creation/validation in tests
- [ ] (B) **Test fixtures with pre-created JWTs** — factory functions that generate valid tokens for test users, skip the OAuth flow in most tests
- [ ] (C) **Both** — OAuth flow tests with mocked Google, plus JWT fixtures for all other endpoint tests that just need an authenticated user
- [ ] (D) Other (describe)

## 9. Error Handling

How verbose should auth error responses be?

- [ ] (A) **Minimal** — generic "Authentication failed" for all auth errors (more secure, harder to debug)
- [ ] (B) **Categorized** — distinguish between "token expired", "invalid token", "account not found" (better UX, slightly more info for attackers)
- [x] (C) **Environment-dependent** — verbose errors in development, minimal in production
- [ ] (D) Other (describe)

## 10. Scope Boundaries

Which of these should be explicitly OUT of scope for this epic?

- [x] (A) RBAC/roles (defer to Epic 03 — Family Management)
- [x] (B) Rate limiting on auth endpoints (defer to security hardening epic)
- [x] (C) Email-based login / password auth (Google OAuth only for MVP)
- [ ] (D) Account deletion / GDPR data export
- [ ] (E) All of the above
- [ ] (F) Other (describe)
