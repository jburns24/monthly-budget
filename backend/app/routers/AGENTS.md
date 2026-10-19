# Routers — AGENTS.md

HTTP layer. A router validates input (Pydantic schemas in `app/schemas/`), resolves auth and
family membership, applies rate limits, calls one service, and maps errors to status codes.
Business logic belongs in `app/services/`.

## API contract (generated)

The route table — method, path, request/response schema, and the `frontend/src/api` module
that calls it — is **generated** from FastAPI's OpenAPI schema into
[docs/api-contract.md](../../../docs/api-contract.md) and [docs/openapi.json](../../../docs/openapi.json)
by `backend/scripts/gen_api_contract.py` (`task be:api-contract`). Do not hand-edit them;
`tests/test_api_contract.py` fails CI when they are stale. After changing a route or schema:
regenerate, then update `frontend/src/types/*` and `frontend/src/api/*` to match. Its
"Frontend paths with no backend route" section flags client calls that would 404.

## Conventions

- Prefix `/api`; family-scoped routes are `/api/families/{family_id}/...` and depend on
  `require_family_member` (or the admin variant) from `app/dependencies.py`.
- Take `uow: UnitOfWork = Depends(get_uow)`; never commit. LLM-backed routes take
  `client = Depends(get_llm_client)`.
- Set `response_model` and explicit `status_code` so the generated contract is accurate.
- Rate-limited routes (`receipts` upload, `categories/suggest`) return 429 with `Retry-After`.
- `dev_auth.py` / `dev_receipts.py` are tagged `dev` and only mounted in development/test;
  they are excluded from the generated contract.

## Auth session guidance

Scoped notes for the cookie/JWT auth surface (`auth.py`, `dev_auth.py`,
`app/services/jwt_service.py`, and the frontend `apiClient` / `useAuth` pair).

### Token lifetimes

| Token | Setting | Env var | Default |
|---|---|---|---|
| Access JWT | `jwt_access_token_expire_minutes` | `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` |
| Refresh JWT | `jwt_refresh_token_expire_days` | `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` |

Defaults live on `Settings` in `app/config.py` and are consumed by
`jwt_service.create_access_token` / `create_refresh_token`. Prefer changing
env (or the ConfigMap in an overlay) over hardcoding new constants.

**Why short access + longer refresh:** access cookies are sent on every `/api/*`
call; keeping them brief limits the window if one leaks. The refresh cookie is
path-scoped to `/api/auth` and is only used to mint a new access token, so a
multi-day lifetime is the real “stay signed in” bound.

`/api/auth/refresh` issues a new access cookie only — it does **not** rotate or
extend the refresh token. After the refresh JWT expires, the user must sign in
again.

### Frontend must refresh on `/api/me`

`GET /api/me` powers `useAuth` / `ProtectedRoute`. That probe **must** go through
`apiClient` (see `frontend/src/hooks/useAuth.ts` → `fetchCurrentUser`).

Raw `fetch('/api/me')` treats an expired access cookie as signed-out and never
calls `/api/auth/refresh`, so users appeared to be kicked after ~15 minutes even
with a still-valid refresh cookie.

`fetchCurrentUser` passes `{ redirectOnAuthFailure: false }` because `Header`
(and thus `useAuth`) also mounts on `/login`. A hard `window.location = /login`
on a missing session would reload the login page in a loop. In-app API calls keep
the default redirect-on-failed-refresh behavior.

### Cookies

Auth cookies are HttpOnly, `SameSite=strict`, and (today) have no `max_age`, so
they are browser session cookies. Closing the browser may clear them even when
the refresh JWT has not expired. `Secure` is off only in development.
