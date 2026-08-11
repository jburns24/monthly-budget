# Auth session guidance

Scoped notes for the cookie/JWT auth surface (`auth.py`, `dev_auth.py`,
`app/services/jwt_service.py`, and the frontend `apiClient` / `useAuth` pair).

## Token lifetimes

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

## Frontend must refresh on `/api/me`

`GET /api/me` powers `useAuth` / `ProtectedRoute`. That probe **must** go through
`apiClient` (see `frontend/src/hooks/useAuth.ts` → `fetchCurrentUser`).

Raw `fetch('/api/me')` treats an expired access cookie as signed-out and never
calls `/api/auth/refresh`, so users appeared to be kicked after ~15 minutes even
with a still-valid refresh cookie.

`fetchCurrentUser` passes `{ redirectOnAuthFailure: false }` because `Header`
(and thus `useAuth`) also mounts on `/login`. A hard `window.location = /login`
on a missing session would reload the login page in a loop. In-app API calls keep
the default redirect-on-failed-refresh behavior.

## Cookies

Auth cookies are HttpOnly, `SameSite=strict`, and (today) have no `max_age`, so
they are browser session cookies. Closing the browser may clear them even when
the refresh JWT has not expired. `Secure` is off only in development.
