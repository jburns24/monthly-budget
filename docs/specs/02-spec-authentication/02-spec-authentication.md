# 02-spec-authentication

## Introduction/Overview

This epic implements Google OAuth 2.0 authentication with PKCE and JWT-based session management for the Monthly Budget application. It creates the `users` and `refresh_token_blacklist` database tables, backend auth endpoints, JWT middleware, and a frontend login flow — establishing the identity layer that all subsequent epics depend on.

The primary goal is: a user can sign in with their Google account, receive HttpOnly cookie-based tokens, and access protected API endpoints. The frontend redirects unauthenticated users to a dedicated login page.

## Goals

- Implement Google OAuth 2.0 login with PKCE (S256) for secure authorization code exchange
- Issue and validate JWT access tokens (15-min) and refresh tokens (7-day) via HttpOnly Secure cookies
- Create the `users` table with Alembic migration, supporting upsert on Google login (create or update `last_login_at`)
- Create the `refresh_token_blacklist` table for durable logout/token invalidation
- Provide a `/me` endpoint returning the current user's profile
- Build a React login page and protect all app routes behind authentication
- Establish reusable auth test infrastructure (mocked Google OAuth, JWT helpers)

## User Stories

- **As a household member**, I want to sign in with my Google account so that I don't need to create or remember a separate password.
- **As a returning user**, I want to stay logged in for up to 7 days so that I don't have to re-authenticate on every visit.
- **As a user**, I want to log out and have my session fully invalidated so that no one can reuse my tokens on a shared device.
- **As a first-time user**, I want to be identified as new after login so that the app can eventually guide me through onboarding.
- **As a developer**, I want a reusable auth dependency (`get_current_user`) so that all future endpoints can easily require authentication.

## Demoable Units of Work

### Unit 1: Database — Users & Token Blacklist

**Purpose:** Create the foundational database tables for identity and session management.

**Functional Requirements:**
- The system shall create a `users` table with columns: `id` (UUID PK), `google_id` (VARCHAR UNIQUE NOT NULL), `email` (VARCHAR UNIQUE NOT NULL), `display_name` (VARCHAR NOT NULL), `avatar_url` (TEXT nullable), `timezone` (VARCHAR DEFAULT 'America/New_York'), `created_at` (TIMESTAMPTZ), `last_login_at` (TIMESTAMPTZ)
- The system shall create a `refresh_token_blacklist` table with columns: `id` (UUID PK), `jti` (VARCHAR UNIQUE NOT NULL), `user_id` (UUID FK to users ON DELETE CASCADE), `expires_at` (TIMESTAMPTZ NOT NULL), `created_at` (TIMESTAMPTZ)
- The system shall create indexes on `refresh_token_blacklist(jti)` and `refresh_token_blacklist(expires_at)`
- The system shall provide the migration via Alembic with both `upgrade` and `downgrade` paths
- The system shall create a SQLAlchemy async ORM model for `User` and `RefreshTokenBlacklist`

**Proof Artifacts:**
- CLI: `alembic upgrade head` succeeds and `alembic downgrade -1` succeeds, demonstrating reversible migration
- CLI: `\dt` in psql shows `users` and `refresh_token_blacklist` tables
- Test: Model unit tests pass, demonstrating ORM models map correctly to the schema

### Unit 2: Backend — OAuth Flow & JWT Endpoints

**Purpose:** Implement the server-side auth endpoints that exchange Google auth codes for JWT cookies.

**Functional Requirements:**
- The system shall add `PyJWT` and `google-auth` to `backend/pyproject.toml` dependencies
- The system shall add CORS middleware to the FastAPI app with `allow_credentials=True`, allowing the frontend origin (`http://localhost:5173` in development), and appropriate methods/headers
- The system shall add startup validation to `config.py`: fail fast if `jwt_secret` is empty or less than 32 characters, or if `google_client_id` is empty, when `ENVIRONMENT != development`
- The system shall expose `POST /api/auth/callback` accepting `{ "code": "...", "code_verifier": "..." }` in the request body
- The system shall exchange the auth code + code_verifier with Google's token endpoint to obtain an `id_token`
- The system shall verify the Google `id_token` signature, `iss`, `aud`, and `exp` claims
- The system shall upsert the user record: create if `google_id` is new, update `last_login_at` and `display_name`/`avatar_url` if existing
- The system shall generate a JWT access token (15-min expiry) with payload: `sub` (google_id), `user_id` (internal UUID), `iat`, `exp`, `jti`
- The system shall generate a JWT refresh token (7-day expiry) with payload: `sub` (google_id), `user_id`, `iat`, `exp`, `jti`
- The system shall set both tokens as HttpOnly, SameSite=Strict cookies. `Secure` flag shall be `True` in production, `False` when `ENVIRONMENT=development`
- The system shall include `is_new_user: true|false` in the callback JSON response so the frontend knows whether to append `?new=true`
- The system shall expose `POST /api/auth/refresh` that validates the refresh token cookie, checks it is not blacklisted, and issues a new access token cookie
- The system shall expose `POST /api/auth/logout` that blacklists the current refresh token's `jti` in the `refresh_token_blacklist` table and clears both cookies
- The system shall expose `GET /api/me` (JWT-protected) returning the current user's `id`, `email`, `display_name`, `avatar_url`, `timezone`
- The system shall expose `PUT /api/me` (JWT-protected) accepting `display_name` and `timezone` updates
- The system shall provide a FastAPI dependency `get_current_user` that extracts and validates the access token from the cookie, returning the `User` ORM object
- The system shall return environment-dependent error detail: verbose messages (e.g., "token expired", "invalid signature") in development, generic "Authentication failed" in production

**Proof Artifacts:**
- Test: OAuth callback test with mocked Google token exchange returns 200 and sets cookies
- Test: `/api/auth/refresh` with valid refresh token returns new access token cookie
- Test: `/api/auth/logout` blacklists the refresh token and clears cookies
- Test: `/api/me` returns 401 without a cookie, 200 with a valid cookie
- Test: `/api/me` PUT updates user fields
- Test: Expired token returns 401
- Test: Blacklisted refresh token returns 401

### Unit 3: Frontend — Login Page & Auth Integration

**Purpose:** Build the login UI and wire up cookie-based auth across the React app.

**Functional Requirements:**
- The system shall render a `/login` page with a "Sign in with Google" button styled with Chakra UI
- The system shall generate a PKCE `code_verifier` (random 43-128 char string) and `code_challenge` (SHA-256 hash, base64url-encoded) in the browser
- The system shall store the `code_verifier` in `sessionStorage` for retrieval after the Google redirect
- The system shall generate a random `state` parameter and store it in `sessionStorage` for CSRF protection
- The system shall read `VITE_GOOGLE_CLIENT_ID` from environment (added to `frontend/.env.example` and `frontend/.env`) and use it to construct the Google OAuth URL
- The system shall redirect the user to Google's OAuth authorization endpoint with `client_id`, `redirect_uri`, `code_challenge`, `code_challenge_method=S256`, `state`, `scope=openid email profile`, and `response_type=code`
- The system shall handle the OAuth callback on a `/auth/callback` route: extract the `code` and `state` from the URL, validate `state` matches sessionStorage, POST `{ code, code_verifier }` to `/api/auth/callback`
- The system shall redirect to `/` on successful login, appending `?new=true` if `is_new_user` is true
- The system shall use React Query to fetch `/api/me` on app load to determine authentication state
- The system shall redirect unauthenticated users to `/login` when they attempt to access any protected route
- The system shall provide a logout button (in a header/nav component) that calls `POST /api/auth/logout` and redirects to `/login`
- The system shall handle 401 responses globally: if any API call returns 401, attempt a silent refresh via `/api/auth/refresh`; if that also fails, redirect to `/login`

**Proof Artifacts:**
- Screenshot: `/login` page renders with Google Sign-In button
- Test: PKCE code_challenge generation produces correct SHA-256 hash (unit test)
- Test: Unauthenticated route access redirects to `/login` (React Testing Library or Playwright)
- Test: Logout clears auth state and redirects to `/login`

### Unit 4: Integration Testing & Auth Test Utilities

**Purpose:** Establish reusable test infrastructure for auth in this and all future epics.

**Functional Requirements:**
- The system shall provide a `create_test_user` factory function that creates a user in the test database and returns the `User` object
- The system shall provide an `authenticated_client` pytest fixture that returns an `httpx.AsyncClient` with valid JWT cookies pre-set
- The system shall provide a `mock_google_oauth` pytest fixture that patches the Google token exchange to return a configurable `id_token`
- The system shall include an integration test that exercises the full flow: OAuth callback → cookie set → `/me` returns user → refresh → logout → `/me` returns 401
- The system shall include a frontend integration test (Vitest + React Testing Library) that verifies the auth redirect flow with mocked API responses

**Proof Artifacts:**
- Test: Full auth flow integration test passes end-to-end
- Test: Auth fixtures are importable and usable in a sample test
- CLI: `task test` passes with all auth tests green

## Non-Goals (Out of Scope)

1. **RBAC / role-based permissions** — roles (`admin`/`member`) are defined in Epic 03 (Family Management). This epic creates users but does not assign roles.
2. **Rate limiting on auth endpoints** — deferred to the security hardening epic per the agreed approach.
3. **Email/password authentication** — Google OAuth is the only auth method for MVP.
4. **Family or group management** — the `families`, `family_members`, and `invites` tables belong to Epic 03.
5. **Account deletion / GDPR data export** — not in scope for this epic.
6. **Onboarding flow UI** — a dedicated onboarding epic will wire together the full post-login experience.

## Design Considerations

- The `/login` page should be clean and minimal: centered card with app logo/name and a single "Sign in with Google" button.
- Use Chakra UI components consistent with the existing `theme.ts` configuration.
- The Google Sign-In button should follow [Google's branding guidelines](https://developers.google.com/identity/branding-guidelines) — use the standard Google "G" logo with "Sign in with Google" text.
- Error states (e.g., OAuth failure, network error) should display inline on the login page, not in a separate error page.
- A simple top navigation bar or header should include the user's avatar/name and a logout button — this will be extended in later epics.

## Repository Standards

- **Backend**: Python 3.12+, FastAPI, async SQLAlchemy 2.0, Alembic for migrations, Pydantic for request/response schemas, structlog for logging, ruff for linting/formatting, mypy for type checking.
- **Frontend**: TypeScript, React 19, Vite, Chakra UI, React Query (TanStack), React Router, Vitest + React Testing Library, ESLint + Prettier.
- **Testing**: pytest with async support (`pytest-asyncio`), httpx `AsyncClient` for API tests, Vitest for frontend unit tests.
- **Docker**: All services run via `docker compose up`. Backend uses multi-stage Dockerfile with non-root user.
- **Code organization**: Backend code in `backend/app/` with `models/`, `schemas/`, `services/`, `routers/` subdirectories. Frontend code in `frontend/src/` with `pages/`, `components/`, `hooks/`, `api/` subdirectories.

## Technical Considerations

- **PKCE implementation**: The frontend must use the Web Crypto API (`crypto.subtle.digest`) for SHA-256 hashing of the code_verifier. Fallback is not needed as all target browsers support it.
- **Google ID token verification**: Use the `google-auth` library (`google.oauth2.id_token.verify_oauth2_token`) or manually verify via Google's JWKS endpoint. The library approach is simpler and handles key rotation.
- **JWT library**: Use `python-jose[cryptography]` or `PyJWT` for token creation and validation. HMAC-SHA256 (`HS256`) with the `JWT_SECRET` from config.
- **Cookie settings**: Access token cookie name `access_token`, refresh token cookie name `refresh_token`. Path `/api` for access token, path `/api/auth/refresh` for refresh token (limits exposure).
- **Token refresh race condition**: The frontend 401 interceptor should queue concurrent requests during a refresh to avoid multiple simultaneous refresh calls.
- **Config validation**: `JWT_SECRET` and `GOOGLE_CLIENT_ID` must be non-empty strings when the auth routes are loaded. Fail fast at startup if missing.
- **Alembic migration**: Must be compatible with the existing empty initial migration from Epic 01.

## Security Considerations

- **JWT_SECRET** must be at least 32 characters of cryptographically random data. Validated at startup.
- **GOOGLE_CLIENT_SECRET** is sensitive and must never be logged or included in error responses.
- **HttpOnly cookies** prevent JavaScript access to tokens, mitigating XSS-based token theft.
- **SameSite=Strict** prevents CSRF attacks by not sending cookies on cross-origin requests.
- **PKCE (S256)** prevents authorization code interception attacks.
- **State parameter** prevents CSRF on the OAuth flow itself.
- **`code_verifier` in sessionStorage** (not localStorage) ensures it's cleared when the tab closes.
- **Roles are NEVER stored in JWT** (per PRD §9.2) — always looked up from the database on each request. This epic does not implement roles but the `get_current_user` dependency must not include role claims in the token.
- **Proof artifacts must NOT contain real tokens, secrets, or credentials.** Test outputs should use sanitized/mock values.

## Success Metrics

1. **Auth flow works end-to-end**: A user can click "Sign in with Google", complete OAuth, and land on the app with a valid session
2. **Token lifecycle is complete**: Access tokens expire after 15 minutes, refresh extends the session, logout invalidates tokens
3. **All tests pass**: Backend auth tests (unit + integration) and frontend auth tests pass via `make test`
4. **No secrets in code or logs**: JWT_SECRET and GOOGLE_CLIENT_SECRET are loaded from environment only, never logged

## Open Questions

1. ~~Should the `GET /api/auth/google/login` endpoint exist as a convenience?~~ **Resolved:** No — the frontend constructs the Google auth URL directly per the PKCE decision (Question 1). A backend convenience endpoint can be added in a future epic if non-browser clients need it.
2. ~~Should we implement a cleanup job for expired entries in `refresh_token_blacklist`?~~ **Resolved:** Deferred to a maintenance epic. The `expires_at` index enables efficient future cleanup queries, and the table will grow slowly (one row per logout).
