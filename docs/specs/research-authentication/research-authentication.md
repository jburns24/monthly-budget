# Research Report: Authentication

**Topic:** Google OAuth 2.0 + JWT Authentication for Monthly Budget
**Date:** 2026-03-23
**Spec Reference:** `docs/specs/02-spec-authentication/02-spec-authentication.md`

---

## Summary

The Monthly Budget codebase (FastAPI backend + React frontend monorepo) completed Epic 01 scaffolding and is fully prepared for authentication implementation. All infrastructure is in place: async SQLAlchemy 2.0 with Alembic migrations, Pydantic v2 settings with auth config fields pre-defined, React Query + React Router + Chakra UI v3 on the frontend, Docker Compose with security-hardened containers, and a CI pipeline with Postgres 16 service.

**Key findings:**

1. **Zero auth code exists** — no models, schemas, routers, middleware, or frontend auth components. All target directories (`models/`, `schemas/`, `services/`, `api/`, `hooks/`, `components/`) are empty stubs ready for implementation.
2. **Config is pre-wired** — `jwt_secret`, `google_client_id`, `google_client_secret` fields exist in `config.py` with empty defaults. Docker Compose and `.env.example` files pass all auth env vars. No startup validation exists yet (need fail-fast for production).
3. **Two backend packages must be added** — `PyJWT` (or `python-jose`) and `google-auth`. No frontend packages are needed (Web Crypto API is native for PKCE).
4. **No CORS middleware configured** — must be added to `main.py` with `allow_credentials=True` for HttpOnly cookie support.
5. **Design decisions are finalized** — 10 key decisions documented in `02-questions-1-authentication.md` covering PKCE flow, cookie strategy, DB blacklist, React Query auth state, and scope boundaries.
6. **Migration chain is clean** — single empty root migration (`e508f2e08a06`); auth migration will be the first real schema change.
7. **Test infrastructure is minimal but extensible** — pytest with `asyncio_mode="auto"`, httpx AsyncClient pattern established, frontend test wrapper with provider stack ready for auth context.

---

## 1. Tech Stack & Project Structure

### Backend Stack
| Component | Version | Source |
|-----------|---------|--------|
| Python | 3.12+ | `pyproject.toml` target |
| FastAPI | >=0.104.0 | `pyproject.toml` |
| SQLAlchemy (async) | >=2.0.0 | `pyproject.toml` |
| Alembic | >=1.13.0 | `pyproject.toml` |
| asyncpg | >=0.29.0 | `pyproject.toml` |
| Pydantic Settings | >=2.1.0 | `pyproject.toml` |
| structlog | >=24.1.0 | `pyproject.toml` |
| Redis | >=5.0.0 | `pyproject.toml` |
| Prometheus Instrumentator | >=6.1.0 | `pyproject.toml` |
| uvicorn | >=0.24.0 | `pyproject.toml` |
| gunicorn | >=21.2.0 | `pyproject.toml` |

### Frontend Stack
| Component | Version | Source |
|-----------|---------|--------|
| React | ^19.2.4 | `package.json` |
| TypeScript | ~5.9.3 | `package.json` |
| Vite | ^8.0.1 | `package.json` |
| React Router | ^7.13.1 | `package.json` |
| Chakra UI | ^3.34.0 | `package.json` |
| TanStack React Query | ^5.95.0 | `package.json` |
| Emotion | ^11.14.0 | `package.json` |
| Framer Motion | ^12.38.0 | `package.json` |

### Package Management
- **Backend:** `uv` (not pip). Lock file: `backend/uv.lock`. Commands: `uv sync`, `uv run <tool>`
- **Frontend:** npm. Lock file: `frontend/package-lock.json`
- **Orchestration:** Taskfile.yml (root) with `backend/Taskfile.yml` and `frontend/Taskfile.yml` includes
- **Dev environment:** Tilt + Docker Compose (live-reload, web UI at localhost:10350)

### Directory Layout

```
backend/app/
├── __init__.py
├── main.py              # FastAPI app with lifespan, Prometheus, router registration
├── config.py            # Pydantic Settings with auth fields pre-defined
├── database.py          # Async engine, AsyncSessionLocal, Base, get_db()
├── logging.py           # Structlog (JSON in prod, console in dev)
├── models/__init__.py   # Empty — auth models go here
├── routers/
│   ├── __init__.py
│   └── health.py        # /api/health, /api/health/ready
├── schemas/__init__.py  # Empty — auth schemas go here
└── services/__init__.py # Empty — auth services go here

frontend/src/
├── main.tsx             # Entry: StrictMode > ChakraProvider > QueryClientProvider > BrowserRouter > App
├── App.tsx              # Routes: only "/" -> HomePage
├── theme.ts             # Chakra UI v3 custom theme (brand color #3182ce)
├── pages/
│   └── HomePage.tsx     # Placeholder with React Query health fetch
├── components/          # Empty
├── hooks/               # Empty
├── api/                 # Empty
└── __tests__/
    └── App.test.tsx     # Test wrapper pattern with providers
```

### Deep-Dive Findings

#### Configuration Validation Gap
`backend/app/config.py` defines auth fields with empty string defaults and **no validators**:
```python
jwt_secret: str = Field(default="", description="JWT signing secret")
google_client_id: str = Field(default="", description="Google OAuth 2.0 client ID")
google_client_secret: str = Field(default="", description="Google OAuth 2.0 client secret")
```
- No `@model_validator` or `@field_validator` decorators exist
- `case_sensitive=False` in SettingsConfigDict (env vars are case-insensitive)
- Properties `is_production` / `is_development` check `environment.lower()`
- **Action needed:** Add startup validation — fail fast if `jwt_secret` < 32 chars or `google_client_id` empty in non-development environments

#### Code Quality Rules
- **Ruff:** `select = ["E", "F", "I", "W"]`, `ignore = ["E501"]`, line-length 120, target py312
- **Mypy:** v1.14.1, `--ignore-missing-imports`, pydantic stubs included
- **TypeScript:** `strict: true`, `noUnusedLocals: true`, `noUnusedParameters: true`, target ES2023
- **ESLint + Prettier:** Frontend enforced via pre-commit
- **detect-secrets:** v1.5.0 with JwtTokenDetector, Base64HighEntropyString, KeywordDetector enabled

#### Frontend Environment Variables
- Only `VITE_API_BASE_URL=http://localhost:8000` exists
- **Missing:** `VITE_GOOGLE_CLIENT_ID` must be added to `frontend/.env.example` and `frontend/.env`
- Vite proxy forwards `/api` to `http://localhost:8000` with `changeOrigin: true` (cookies pass through)

---

## 2. Architecture & Patterns

### FastAPI App Structure (`backend/app/main.py`)

**Registration order:**
1. Lifespan handler (startup logging, shutdown engine dispose)
2. FastAPI app creation (`debug=settings.debug`, `lifespan=lifespan`)
3. Prometheus instrumentation (`Instrumentator().instrument(app).expose(app)`)
4. Router registration (`app.include_router(health.router)`)

**Integration points for auth:**
- **CORS middleware:** Add after Prometheus, before routers — `app.add_middleware(CORSMiddleware, allow_credentials=True, ...)`
- **Auth router:** `app.include_router(auth.router)` after health router
- **Users router:** `app.include_router(users.router)` after auth router

### Database Layer (`backend/app/database.py`)

```python
engine = create_async_engine(settings.database_url, echo=settings.debug, pool_pre_ping=True, pool_size=5, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

**Key properties:** `expire_on_commit=False` (objects usable after commit), `autoflush=False` (explicit control), `pool_pre_ping=True` (connection validation).

**Model registration for Alembic:** Models inheriting from `Base` must be imported before `alembic revision --autogenerate`. The `alembic/env.py` imports `Base` from `app.database` and uses `target_metadata = Base.metadata`.

### Router Pattern (`backend/app/routers/health.py`)

```python
router = APIRouter(prefix="/api/health", tags=["health"])
logger = get_logger(__name__)

@router.get("")
async def health(response: Response) -> dict:
    db_ok, db_status = await _check_database()
    if not all_ok:
        response.status_code = 503
    return {"status": "healthy" if all_ok else "degraded", ...}
```

**Pattern:** Prefix on router (not app), async handlers, structlog logger, private helper functions with `_` prefix, manual status code via `Response` parameter.

### Frontend Provider Hierarchy (`frontend/src/main.tsx`)

```
StrictMode > ChakraProvider > QueryClientProvider > BrowserRouter > App
```

**AuthProvider insertion point:** After BrowserRouter, before App — gives access to both React Query and Router APIs:
```tsx
<BrowserRouter>
  <AuthProvider>  {/* NEW */}
    <App />
  </AuthProvider>
</BrowserRouter>
```

### Frontend Route Structure (`frontend/src/App.tsx`)

Currently single route: `<Route path="/" element={<HomePage />} />`

**Auth routes to add:**
- `/login` — Public (LoginPage)
- `/auth/callback` — Public (OAuth callback handler)
- `/` — Protected (HomePage wrapped in ProtectedRoute)
- `/*` — Catch-all redirect

### React Query Fetch Pattern (`frontend/src/pages/HomePage.tsx`)

```typescript
const { data, isLoading, error } = useQuery<HealthResponse>({
  queryKey: ['health'],
  queryFn: async () => {
    const response = await fetch('/api/health')
    if (!response.ok) throw new Error('Health check failed')
    return response.json()
  },
})
```

**Auth-aware changes needed:** Add `credentials: 'include'` to fetch calls, handle 401 with silent refresh attempt, key queries by user for cache invalidation on login/logout.

---

## 3. Dependencies & Integrations

### Missing Backend Packages (Must Add)

| Package | Purpose | Required |
|---------|---------|----------|
| `PyJWT>=2.8.0` | JWT token creation/validation (HS256) | Yes |
| `google-auth>=2.25.0` | Google ID token verification via JWKS | Yes |

**Note:** Spec mentions `python-jose[cryptography]` as alternative to PyJWT. PyJWT is simpler and more Pythonic.

### Missing Frontend Packages

None required. The Web Crypto API (`crypto.subtle.digest`) handles PKCE SHA-256 natively. No `jwt-decode` needed since tokens are HttpOnly (not accessible to JS).

### Docker Compose Services

| Service | Image | Port | Health Check |
|---------|-------|------|-------------|
| api | custom (multi-stage) | 8000 | `GET /api/health` every 30s |
| db | postgres:16-alpine | 5432 | `pg_isready` every 10s |
| redis | redis:7-alpine | 6379 | `redis-cli ping` every 10s |
| frontend | custom (Node 20) | 5173 | None |

**Security hardening (all services):**
- Read-only filesystem (`read_only: true`) with writable `/tmp` (noexec, nosuid)
- `no-new-privileges:true`, `cap_drop: ALL`
- Non-root user (UID 1001 `appuser` for API)
- Resource limits (512MB/1CPU for API, 256MB/0.5CPU for frontend)

**Auth env vars passed to API container:**
```yaml
SECRET_KEY: ${SECRET_KEY}
JWT_SECRET: ${JWT_SECRET}
GOOGLE_CLIENT_ID: ${GOOGLE_CLIENT_ID}
GOOGLE_CLIENT_SECRET: ${GOOGLE_CLIENT_SECRET}
ENVIRONMENT: ${ENVIRONMENT:-development}
```

### Entrypoint Script (`backend/entrypoint.sh`)

Runs `alembic upgrade head` before starting gunicorn — guarantees auth tables exist before the server accepts traffic.

### Environment Files

**Root `.env.example`:**
```bash
SECRET_KEY=changeme_secret_key_min_32_chars_long
JWT_SECRET=changeme_jwt_secret_min_32_chars_long
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your-google-client-secret
ENVIRONMENT=development
```

**Backend `.env.example`:** Same auth vars with minimal placeholders (`change-me`).

**Frontend `.env.example`:** Only `VITE_API_BASE_URL=http://localhost:8000` — needs `VITE_GOOGLE_CLIENT_ID`.

### CORS Configuration

**Current state:** Not configured. Must add to `main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[...],  # Dev: localhost:5173; prod: actual domain
    allow_credentials=True,  # Required for HttpOnly cookies
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)
```

---

## 4. Test & Quality Patterns

### Backend Test Setup

**Configuration:** `asyncio_mode = "auto"` in `pyproject.toml`, `testpaths = ["tests"]`

**Dependencies:** pytest >=7.4.0, pytest-asyncio >=0.23.0, httpx >=0.25.0

**Current fixtures (`backend/tests/conftest.py`):**
```python
@pytest.fixture
def anyio_backend():
    return "asyncio"
```

**Established test pattern (`backend/tests/test_placeholder.py`):**
```python
@pytest.mark.asyncio
async def test_health_endpoint_schema() -> None:
    from app.main import app
    with patch("app.routers.health._check_database", new_callable=AsyncMock, return_value=(True, "connected")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/health")
            assert response.status_code == 200
```

**Auth fixtures to create:**
- `db_session` — Async session with transaction rollback per test
- `create_test_user` — Factory that inserts a User and returns the object
- `authenticated_client` — AsyncClient with valid JWT cookies pre-set
- `mock_google_oauth` — Patches Google token exchange to return configurable `id_token`

**Dependency override pattern:** `app.dependency_overrides[get_db] = mock_get_db`

### Frontend Test Setup

**Configuration (`vite.config.ts`):**
```typescript
test: {
  globals: true,
  environment: 'happy-dom',
  setupFiles: ['./src/setupTests.ts'],
  css: true,
  server: { deps: { inline: [/@chakra-ui/, /framer-motion/] } },
}
```

**Test wrapper pattern (`src/__tests__/App.test.tsx`):**
```typescript
function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }) => (
    <MemoryRouter>
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </ChakraProvider>
    </MemoryRouter>
  )
}
```

**Auth test extension:** Add AuthProvider or mock auth context to wrapper; mock `/api/me` responses for authenticated/unauthenticated states.

### CI Pipeline (`.github/workflows/ci.yml`)

**3 jobs:**

1. **pre-commit** — Runs ruff, mypy, eslint, prettier, tsc, detect-secrets on all files
2. **backend-tests** — Postgres 16 service, env: `DATABASE_URL`, `SECRET_KEY=ci-test-secret-key`, `ENVIRONMENT=test`. Command: `uv sync && uv run pytest`
3. **frontend-tests** — `npm ci && npm test -- --run`

**CI auth implications:**
- Postgres available for real DB tests (migrations auto-applied)
- `JWT_SECRET` not set in CI (falls back to empty string) — auth tests must set it via fixture or env override
- `ENVIRONMENT=test` — can be checked in config for test-specific behavior

### Pre-commit Hooks

| Hook | Scope | Impact on Auth Code |
|------|-------|---------------------|
| ruff check | Python | Import sorting, unused vars, style |
| ruff format | Python | Auto-formatting (120 char lines) |
| mypy | Python | Type hints required |
| eslint | TypeScript | Linting rules |
| prettier | TypeScript | Formatting (100 char lines) |
| tsc --noEmit | TypeScript | Strict type checking |
| detect-secrets | All | No hardcoded tokens/keys in code |

### Alembic Migration Setup (`backend/alembic/env.py`)

- Async migration via `async_engine_from_config` with `pool.NullPool`
- `target_metadata = Base.metadata` (line 30) — auto-discovers models
- URL override: `config.set_main_option("sqlalchemy.url", settings.database_url)` (line 21)
- Models must be imported into scope where `Base` is defined for autogenerate to work

---

## 5. Data Models & API Surface

### Existing Migration Chain

**Root migration:** `e508f2e08a06_initial_empty_migration.py`
- `revision = "e508f2e08a06"`
- `down_revision = None`
- Both `upgrade()` and `downgrade()` are no-ops (`pass`)
- Next migration must set `down_revision = "e508f2e08a06"`

### Planned Auth Schema (from Spec)

**`users` table:**
```sql
id              UUID PRIMARY KEY
google_id       VARCHAR UNIQUE NOT NULL
email           VARCHAR UNIQUE NOT NULL
display_name    VARCHAR NOT NULL
avatar_url      TEXT (nullable)
timezone        VARCHAR DEFAULT 'America/New_York'
created_at      TIMESTAMPTZ
last_login_at   TIMESTAMPTZ
```

**`refresh_token_blacklist` table:**
```sql
id              UUID PRIMARY KEY
jti             VARCHAR UNIQUE NOT NULL
user_id         UUID FK -> users(id) ON DELETE CASCADE
expires_at      TIMESTAMPTZ NOT NULL
created_at      TIMESTAMPTZ

INDEXES: (jti), (expires_at)
```

### UUID Strategy

No UUID usage exists in the codebase yet. Recommended pattern:
- Python-side generation: `uuid.uuid4()` as default factory
- SQLAlchemy column: `Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)`
- PostgreSQL stores as native UUID type via asyncpg

### Planned Auth Endpoints (from Spec)

| Endpoint | Method | Auth | Request Body | Response |
|----------|--------|------|-------------|----------|
| `/api/auth/callback` | POST | None | `{code, code_verifier}` | `{is_new_user}` + Set-Cookie |
| `/api/auth/refresh` | POST | Refresh cookie | None | Set-Cookie (new access token) |
| `/api/auth/logout` | POST | Access cookie | None | Clear cookies |
| `/api/me` | GET | Access token | None | `{id, email, display_name, avatar_url, timezone}` |
| `/api/me` | PUT | Access token | `{display_name?, timezone?}` | Updated user |

### JWT Token Structure (from Spec)

**Access token (15-min):** `{sub: google_id, user_id: uuid, iat, exp, jti}`
**Refresh token (7-day):** `{sub: google_id, user_id: uuid, iat, exp, jti}`
**Algorithm:** HS256 with `JWT_SECRET`

**Cookie settings:**
- Access: name `access_token`, path `/api`, HttpOnly, SameSite=Strict, Secure (env-dependent)
- Refresh: name `refresh_token`, path `/api/auth/refresh`, HttpOnly, SameSite=Strict, Secure (env-dependent)

### Frontend Type Definitions

Currently only one ad-hoc interface exists (`HealthResponse` in `HomePage.tsx`). No centralized type definitions. Need to establish:
- `frontend/src/types/` directory
- `User` interface matching `/api/me` response
- `AuthCallbackResponse` interface
- API client abstraction in `frontend/src/api/`

### Design Decisions (from `02-questions-1-authentication.md`)

| # | Decision | Selection |
|---|----------|-----------|
| 1 | OAuth flow | Frontend-initiated PKCE |
| 2 | Token storage | HttpOnly cookies (Secure=False in dev) |
| 3 | Tables scope | Only `users` + `refresh_token_blacklist` |
| 4 | Post-login redirect | `/` with `?new=true` for first-time users |
| 5 | Refresh strategy | DB blacklist table (not Redis) |
| 6 | Frontend auth state | React Query + `/api/me` |
| 7 | Protected routes | Redirect to `/login` page |
| 8 | Testing | Mock Google OAuth, real JWT |
| 9 | Error handling | Environment-dependent verbosity |
| 10 | Scope exclusions | No RBAC, rate limiting, email auth |

---

## Files to Create (Auth Implementation)

### Backend
| File | Purpose |
|------|---------|
| `backend/app/models/user.py` | User ORM model |
| `backend/app/models/refresh_token_blacklist.py` | RefreshTokenBlacklist ORM model |
| `backend/app/schemas/auth.py` | Auth request/response Pydantic schemas |
| `backend/app/schemas/user.py` | User response/update schemas |
| `backend/app/routers/auth.py` | Auth endpoints (callback, refresh, logout) |
| `backend/app/routers/users.py` | User endpoints (GET/PUT /me) |
| `backend/app/services/auth.py` | OAuth + JWT business logic |
| `backend/app/dependencies.py` | `get_current_user()` dependency |
| `backend/alembic/versions/xxx_create_auth_tables.py` | Migration (autogenerated) |
| `backend/tests/conftest.py` | Extended with auth fixtures |
| `backend/tests/test_auth.py` | Auth endpoint tests |
| `backend/tests/test_users.py` | User endpoint tests |

### Frontend
| File | Purpose |
|------|---------|
| `frontend/src/pages/LoginPage.tsx` | Login UI with Google Sign-In button |
| `frontend/src/pages/AuthCallbackPage.tsx` | OAuth callback handler |
| `frontend/src/components/ProtectedRoute.tsx` | Route guard wrapper |
| `frontend/src/components/Header.tsx` | Nav with user avatar + logout |
| `frontend/src/hooks/useAuth.ts` | Auth state hook (React Query + /api/me) |
| `frontend/src/api/auth.ts` | Auth API calls |
| `frontend/src/utils/pkce.ts` | PKCE code_verifier/challenge generation |
| `frontend/src/types/api.ts` | Shared API response types |

### Files to Modify
| File | Change |
|------|--------|
| `backend/app/main.py` | Add CORS middleware, include auth + users routers |
| `backend/app/config.py` | Add startup validation for auth secrets |
| `backend/app/database.py` | Import auth models for Alembic |
| `backend/app/models/__init__.py` | Export User, RefreshTokenBlacklist |
| `backend/pyproject.toml` | Add PyJWT, google-auth |
| `frontend/src/main.tsx` | Add AuthProvider in provider hierarchy |
| `frontend/src/App.tsx` | Add login, callback, protected routes |
| `frontend/.env.example` | Add VITE_GOOGLE_CLIENT_ID |
| `.env.example` | Add VITE_GOOGLE_CLIENT_ID |

---

## Meta-Prompt for /cw-spec

---

**Feature name:** Authentication — Google OAuth 2.0 + JWT Session Management

**Problem statement:** The Monthly Budget app has no user identity layer. Users cannot log in, and all API endpoints are unprotected. This epic establishes Google OAuth 2.0 login with PKCE, JWT-based session management via HttpOnly cookies, and frontend route protection — forming the foundation for all subsequent user-scoped features.

**Key components to modify or create:**
- Backend: `models/user.py`, `models/refresh_token_blacklist.py`, `schemas/auth.py`, `schemas/user.py`, `routers/auth.py`, `routers/users.py`, `services/auth.py`, `dependencies.py`
- Frontend: `pages/LoginPage.tsx`, `pages/AuthCallbackPage.tsx`, `components/ProtectedRoute.tsx`, `components/Header.tsx`, `hooks/useAuth.ts`, `api/auth.ts`, `utils/pkce.ts`, `types/api.ts`
- Modifications: `main.py` (CORS + routers), `config.py` (validation), `database.py` (model imports), `pyproject.toml` (deps), `App.tsx` (routes), `main.tsx` (AuthProvider)

**Architectural constraints discovered:**
- All backend code must be async (async SQLAlchemy, async routes, async tests)
- Models must be imported into `database.py` for Alembic autogenerate to detect them
- Migration must chain from `down_revision = "e508f2e08a06"` (initial empty migration)
- CORS middleware with `allow_credentials=True` required for HttpOnly cookies
- Frontend TypeScript strict mode: no unused vars/params, complete type coverage required
- Docker read-only filesystem — no disk I/O in auth paths (all cookie/DB-based)
- Pre-commit enforces ruff, mypy, eslint, prettier, tsc, detect-secrets

**Patterns to follow (with file references):**
- Router pattern: `backend/app/routers/health.py` (APIRouter with prefix, tags, async handlers, structlog)
- DB dependency: `backend/app/database.py:get_db()` (async generator, commit/rollback/close)
- Config pattern: `backend/app/config.py` (Pydantic Settings, env-based, `is_production` property)
- Logging: `backend/app/logging.py:get_logger()` (structlog, JSON in prod, console in dev)
- React Query: `frontend/src/pages/HomePage.tsx` (useQuery with queryKey, queryFn, error handling)
- Test wrapper: `frontend/src/__tests__/App.test.tsx:createWrapper()` (MemoryRouter + ChakraProvider + QueryClientProvider)
- Test pattern: `backend/tests/test_placeholder.py` (AsyncClient + ASGITransport + AsyncMock + patch)

**Suggested demoable units (from spec):**
1. Database — Users & Token Blacklist (Alembic migration, ORM models, model unit tests)
2. Backend — OAuth Flow & JWT Endpoints (auth callback, refresh, logout, /me, get_current_user dependency)
3. Frontend — Login Page & Auth Integration (login UI, PKCE, OAuth callback, protected routes, 401 handling)
4. Integration Testing & Auth Test Utilities (fixtures, factories, full-flow integration test)

**Code references:**
- `backend/app/main.py` — FastAPI app entry point, middleware + router registration
- `backend/app/config.py` — Settings with auth fields (lines 55-70)
- `backend/app/database.py` — Async engine, Base, get_db() dependency
- `backend/app/routers/health.py` — Router pattern template
- `backend/alembic/env.py` — Async migration setup, target_metadata
- `backend/alembic/versions/e508f2e08a06_initial_empty_migration.py` — Root migration
- `frontend/src/main.tsx` — Provider hierarchy (ChakraProvider > QueryClientProvider > BrowserRouter)
- `frontend/src/App.tsx` — Route definitions
- `frontend/src/pages/HomePage.tsx` — React Query fetch pattern
- `frontend/vite.config.ts` — Proxy config (lines 13-20), test config (lines 22-32)
- `docs/specs/02-spec-authentication/02-spec-authentication.md` — Full specification
- `docs/specs/02-spec-authentication/02-questions-1-authentication.md` — Design decisions

---
