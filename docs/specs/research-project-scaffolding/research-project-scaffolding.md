# CW-Research Report: Project Scaffolding

**Topic:** Project Scaffolding (Epic 01)
**Date:** 2026-03-22
**Status:** Greenfield project (no source code exists)
**Spec:** `docs/specs/01-spec-project-scaffolding/01-spec-project-scaffolding.md`

---

## Summary

This research covers the complete scaffolding requirements for the Monthly Budget application — a self-hosted, privacy-first family budget tracker with receipt scanning via Claude AI. The project is **greenfield** with only a PRD and spec document in the repository.

**Key findings across all dimensions:**

1. **Tech Stack:** Python 3.12+ (FastAPI/uv) backend + React 18+ (Vite/TypeScript/npm) frontend, PostgreSQL 16, Redis 7, all orchestrated via Docker Compose with security hardening
2. **Architecture:** Async-first backend (SQLAlchemy 2.0 async + asyncpg), defense-in-depth security (PostgreSQL RLS + API checks + JWT with roles never in token), family-as-tenant model
3. **Dependencies:** 60+ libraries across backend/frontend; external integrations with Google OAuth 2.0 (PKCE) and Anthropic Claude API (claude-haiku-4-5-20251001)
4. **Quality:** Pre-commit as single source of truth for all lint/format/type checks; GitHub Actions CI mirrors local checks identically; 80%+ business logic coverage target
5. **Data Model:** 10 database tables with integer-cents arithmetic, soft deletes, optimistic locking, year_month denormalization, and pg_trgm trigram indexing for category suggestion

---

## 1. Tech Stack & Project Structure

### 1.1 Language & Runtime Requirements

| Component | Technology | Version | Source |
|-----------|-----------|---------|--------|
| Backend | Python | 3.12+ | PRD §7.2 |
| Frontend | TypeScript (strict) | Latest | Spec Unit 2 |
| Node.js | Runtime | 20+ | PRD §18 |
| PostgreSQL | Database | 16 Alpine | PRD §7.2, Spec Unit 3 |
| Redis | Cache/Sessions | 7 Alpine | PRD §7.2, Spec Unit 3 |

### 1.2 Backend Stack

| Layer | Technology | Config Location |
|-------|-----------|-----------------|
| Framework | FastAPI | `backend/app/main.py` |
| Server | Gunicorn + Uvicorn workers (4 workers) | Dockerfile ENTRYPOINT |
| ORM | SQLAlchemy 2.0 (async) + asyncpg | `backend/app/database.py` |
| Migrations | Alembic (async, `run_async_migrations` pattern) | `backend/alembic/env.py` |
| Config | Pydantic v2 BaseSettings | `backend/app/config.py` |
| Logging | structlog (JSON prod / Console dev) | `backend/app/logging.py` |
| Metrics | prometheus-fastapi-instrumentator | `backend/app/main.py` |
| Linting | ruff (lint + format) | `backend/pyproject.toml` |
| Type Check | mypy or pyright | `.pre-commit-config.yaml` |
| Testing | pytest + pytest-asyncio + httpx | `backend/pyproject.toml` |
| Deps | uv (generates `uv.lock`) | `backend/pyproject.toml` |

### 1.3 Frontend Stack

| Layer | Technology | Config Location |
|-------|-----------|-----------------|
| Framework | React 18+ | `frontend/src/App.tsx` |
| Build | Vite | `frontend/vite.config.ts` |
| UI Library | Chakra UI (custom theme) | `frontend/src/theme.ts` |
| Routing | React Router v6+ | `frontend/src/App.tsx` |
| State | TanStack Query (React Query) | `frontend/src/App.tsx` |
| Linting | ESLint | `frontend/.eslintrc.cjs` |
| Formatting | Prettier | `frontend/.prettierrc.json` |
| Type Check | tsc --noEmit | `frontend/tsconfig.json` |
| Testing | Vitest + React Testing Library | `frontend/vitest.config.ts` |
| Deps | npm (generates `package-lock.json`) | `frontend/package.json` |

### 1.4 Required Directory Structure

```
monthly-budget/
├── .github/workflows/ci.yml
├── .pre-commit-config.yaml
├── .secrets.baseline
├── docker-compose.yml
├── Makefile
├── README.md
├── .gitignore
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── logging.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── routers/
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   ├── tests/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── uv.lock
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── theme.ts
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   └── api/
│   ├── public/
│   │   └── manifest.json
│   ├── vite.config.ts
│   ├── vitest.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   ├── package-lock.json
│   ├── Dockerfile
│   └── .env.example
└── docs/
```

### Deep-Dive Findings

**Gunicorn Configuration:**
- 4 Uvicorn workers, bound to `0.0.0.0:8000`
- `--reload` only in dev (run uvicorn directly); never with Gunicorn in production
- 120s timeout to accommodate Claude API receipt processing calls

**Alembic Async Pattern:**
- `env.py` uses `asyncio.run(run_async_migrations())` for online mode
- `create_async_engine` with `pool.NullPool` for migration connections
- Must import all models for autogenerate to discover metadata

**structlog Configuration:**
- Production: `TimeStamper(fmt="iso")` → `JSONRenderer()`
- Development: `TimeStamper(fmt="iso")` → `ConsoleRenderer()`
- Switched via `ENVIRONMENT` env var
- Sanitization middleware strips API keys, passwords, tokens from log context

**Prometheus Metrics:**
- `Instrumentator().instrument(app).expose(app)` auto-instruments all HTTP endpoints
- Custom metrics: `receipt_processing_total` (Counter), `receipt_processing_duration_seconds` (Histogram)
- `/metrics` endpoint excluded from auth in later epics

**Vite HMR in Docker:**
- Must bind to `--host` for external connections from Docker bridge network
- Volume mounts for `src/` and `public/` enable hot-reload
- Exclude `node_modules` from volume mount to prevent host shadowing

**Version Strategy:** Ranges in manifests + lockfiles (`uv.lock`, `package-lock.json`) for reproducibility.

---

## 2. Architecture & Patterns

### 2.1 System Architecture

```
Home Network (Self-Hosted)
  ├── Tailscale VPN (encrypted tunnel, zero-config HTTPS)
  ├── Caddy Reverse Proxy (TLS, rate limiting, security headers)  [not in Epic 01]
  ├── FastAPI Backend (async Python, Gunicorn + Uvicorn workers)
  │   └── Async SQLAlchemy ORM + asyncpg
  ├── PostgreSQL 16 (financial data, RLS, encryption)
  ├── Redis 7 (sessions, rate limit counters, ephemeral only)
  └── Receipt Storage (dedicated volume)
```

### 2.2 Backend Patterns

**API Structure:** REST at `/api/v1` with resource-oriented endpoints. Amounts as integer cents. ISO 8601 timestamps. Pagination via `?page=1&per_page=50`.

**Dependency Injection:** FastAPI `Depends()` for `get_db()` session, `get_current_user()` auth, role checks.

**Error Handling:** Centralized exception handler returning `{"error": {"code": "...", "message": "...", "details": {...}}}`.

**Configuration:** Pydantic `BaseSettings` loads env vars first, then `.env` file. Fails fast on missing required vars. Secret loading supports both env vars (dev) and file mounts (prod K8s).

### 2.3 Frontend Patterns

**Component Architecture:** Pages (route-level) → Components (reusable UI) → Hooks (data/logic).

**State Management:** TanStack Query for server state (expenses, categories, goals). React context for client state (auth, UI). `staleTime: 60s`, `refetchOnWindowFocus: true`.

**Routing:** React Router v6 with lazy loading via `React.lazy()` + `<Suspense>`. Code-split per major feature.

**Mobile-First Design (PRD §6.4):**
- Thumb-zone optimized: primary actions in bottom 60% of viewport
- 44px min / 48px preferred touch targets
- Single-column layout, no horizontal scrolling
- `inputMode="decimal"` for amounts, native `type="date"` for dates
- Safe area insets for iPhone notch/home indicator
- System font stack: `font-family: system-ui`

### 2.4 Security Architecture

**Authentication:** Google OAuth 2.0 with PKCE (S256). No password storage.

**JWT Design:**
- Access token: 15 min, HMAC-SHA256 with 256-bit secret
- Refresh token: 7 days, HttpOnly + Secure + SameSite=Strict cookie
- **Roles (admin/member) NEVER in JWT** — always looked up from DB per request

**Defense in Depth:**
1. PostgreSQL RLS (row-level security) enforces family isolation at DB layer
2. API-level family membership validation on every request
3. JWT authentication with per-request role lookup
4. Audit logging for non-repudiation

**Container Security (PRD §17):**
- Multi-stage Docker builds (builder + runtime)
- Non-root user (`appuser:appgroup`)
- `read_only: true` filesystem with tmpfs for `/tmp`
- `cap_drop: ALL` (PostgreSQL adds back CHOWN, SETUID, SETGID, FOWNER, DAC_READ_SEARCH)
- `security_opt: no-new-privileges:true`

### Deep-Dive Findings

**STRIDE Threat Model (12 threats identified):**

| ID | Threat | Key Mitigation |
|----|--------|----------------|
| T1 | JWT forgery | 256-bit HMAC-SHA256, quarterly rotation, 15-min TTL |
| T2 | Role escalation | Roles in DB only, never JWT; checked every request |
| T3 | Cross-family IDOR | PostgreSQL RLS + API family validation |
| T4 | Repudiation | Immutable audit log (REVOKE DELETE on audit_log) |
| T5 | Malicious receipt | Magic-byte validation, Pillow re-encoding, 5MB limit |
| T6 | API key leak | K8s Secrets as files, log sanitization, detect-secrets |
| T7 | OAuth replay | PKCE (S256), single-use codes, state parameter |
| T8 | DDoS | Tailscale VPN restriction + Caddy rate limiting |
| T9 | SQL injection | SQLAlchemy ORM (parameterized) + Pydantic validation |
| T10 | CSV cross-family leak | RLS on export query + server-side membership check |
| T11 | Session hijacking | HttpOnly+Secure+SameSite=Strict, 24h expiry |
| T12 | K8s privilege escalation | PSS, minimal RBAC, no automount service account token |

**PostgreSQL cap_add Requirements:**
- `CHOWN`: Change file ownership during init
- `SETUID`: Switch to postgres user
- `SETGID`: Switch to postgres group
- `FOWNER`: Override file ownership checks for WAL recovery
- `DAC_READ_SEARCH`: Read /dev/null, /dev/random, shared memory

**Redis Configuration:**
- `--requirepass` for AUTH on every command
- `--maxmemory 128mb --maxmemory-policy allkeys-lru`
- `--save "" --appendonly no` (ephemeral, no persistence)

**Read-Only Filesystem Writable Paths:**
- API: `/tmp` (tmpfs), `/data/receipts` (volume)
- PostgreSQL: `/var/lib/postgresql/data` (volume), `/tmp` (tmpfs), `/run/postgresql` (tmpfs)
- Redis: `/tmp` (tmpfs), in-memory only

---

## 3. Dependencies & Integrations

### 3.1 Backend Python Dependencies

**Core:**
- fastapi, gunicorn, uvicorn — Web framework & server
- sqlalchemy[asyncio], asyncpg — Async ORM & DB driver
- alembic — Database migrations
- pydantic, pydantic-settings — Validation & config
- structlog — Structured logging
- prometheus-fastapi-instrumentator — Metrics
- redis (or aioredis) — Redis client
- httpx — Async HTTP client

**Auth & Security:**
- PyJWT — JWT signing/validation
- Authlib — OAuth 2.0 client (Google)
- python-magic — File magic-byte validation
- Pillow — Image re-encoding for receipt security

**Dev/Test:**
- ruff — Linting + formatting
- mypy or pyright — Type checking
- pytest, pytest-asyncio — Testing
- httpx (AsyncClient) — Integration testing

### 3.2 Frontend npm Dependencies

**Core:**
- react, react-dom — UI framework
- typescript — Language
- vite, @vitejs/plugin-react — Build tool
- @chakra-ui/react, @emotion/react, @emotion/styled — UI components
- react-router-dom — Routing
- @tanstack/react-query — Server state management

**Dev/Test:**
- eslint, @typescript-eslint/* — Linting
- prettier — Formatting
- vitest, @testing-library/react, @testing-library/jest-dom — Testing
- jsdom — Test environment

### 3.3 External Service Integrations

**Google OAuth 2.0:**
- PKCE flow with S256 challenge
- Client ID/Secret in `.env` (dev) / K8s Secrets (prod)
- Endpoints: `/auth/google/login`, `/auth/google/callback`

**Anthropic Claude API:**
- Model: `claude-haiku-4-5-20251001` (pinned, not latest)
- Receipt parsing via tool use (structured output)
- Cost: ~$0.0015/receipt (~$0.09/month for family of 4)
- Rate limit: 10 req/min per user

### 3.4 Inter-Service Communication

- **Vite Proxy (dev):** `/api` → `http://localhost:8000` (avoids CORS)
- **Docker Network:** Shared bridge network for all 4 services
- **Service Dependencies:** API depends on DB + Redis with `condition: service_healthy`
- **Startup:** API runs `alembic upgrade head` before starting server

---

## 4. Test & Quality Patterns

### 4.1 Pre-Commit Configuration (Single Source of Truth)

**`.pre-commit-config.yaml`** defines ALL code quality checks:

| Hook | Language | Purpose |
|------|----------|---------|
| `ruff check` | system | Backend Python linting |
| `ruff format --check` | system | Backend Python formatting |
| `mypy` or `pyright` | python | Backend type checking |
| `eslint` | node | Frontend linting |
| `prettier --check` | node | Frontend formatting |
| `tsc --noEmit` | node | Frontend type checking |
| `trailing-whitespace` | built-in | Trim trailing whitespace |
| `end-of-file-fixer` | built-in | Ensure newline at EOF |
| `check-yaml` | built-in | YAML syntax validation |
| `check-added-large-files` | built-in | Prevent large file commits |
| `detect-secrets` | python | Secret scanning (with `.secrets.baseline`) |

**Language Strategy:**
- `language: system` for ruff (uses project-local binary via uv)
- `language: python` for mypy, detect-secrets (isolated environments)
- `language: node` for eslint, prettier, tsc (uses npm dependencies)

### 4.2 GitHub Actions CI Pipeline

**`.github/workflows/ci.yml`:**

```
Jobs:
  1. pre-commit: pre-commit/action@v3.0.0 → pre-commit run --all-files
  2. backend-tests: pytest against PostgreSQL service container (postgres:16-alpine)
  3. frontend-tests: vitest run
```

**Caching:**
- Pre-commit environments: cached by `pre-commit/action`
- Python/uv: `actions/setup-python` with `cache: 'uv'`
- npm: `actions/setup-node` with `cache: 'npm'`, key from `package-lock.json`

**Tests are NOT in pre-commit** (require database / can be slow). They run as separate CI jobs.

### 4.3 Makefile Commands

| Target | Command | Purpose |
|--------|---------|---------|
| `make lint` | `pre-commit run --all-files` | All quality checks |
| `make test` | pytest + vitest | All tests |
| `make up` | `docker compose up -d` | Start stack |
| `make down` | `docker compose down` | Stop stack |

### 4.4 Coverage Targets

- **Unit Tests:** 80%+ business logic (both backend and frontend)
- **Integration Tests:** All endpoints, happy + error paths
- **E2E Tests:** 5 critical user flows via Playwright (future epics)

### Deep-Dive Findings

**detect-secrets Baseline Setup:**
```bash
detect-secrets scan > .secrets.baseline
```
- `.secrets.baseline` committed to repo
- Marks known non-secrets (placeholder values in `.env.example`)
- Pre-commit hook: `--baseline .secrets.baseline` argument

**PostgreSQL Service Container in CI:**
- Image: `postgres:16-alpine` with `pg_isready` health check
- Test database: `monthly_budget_test` with test credentials
- Steps: health check → `uv sync` → `alembic upgrade head` → `pytest`

**Identical Checks Guarantee:**
- Same `.pre-commit-config.yaml` read by both local hooks and CI
- Version pinning via `rev:` in config prevents tool drift
- `--all-files` in CI catches bypassed local hooks (`git commit --no-verify`)

---

## 5. Data Models & API Surface

### 5.1 Epic 01 API Endpoints

| Method | Endpoint | Auth | Response |
|--------|----------|------|----------|
| GET | `/api/health` | None | `{"status": "healthy", "database": "connected", "redis": "connected"}` (200/503) |
| GET | `/api/health/ready` | None | 200 if migrations current, 503 otherwise |
| GET | `/metrics` | None | Prometheus text format |
| GET | `/docs` | None | Auto-generated OpenAPI |

### 5.2 Full API Surface (All Epics)

**Authentication:** `/auth/google/login`, `/auth/google/callback`, `/auth/refresh`, `/auth/logout`, `/me`

**Families:** POST/GET `/families`, POST `/families/{id}/invites`, GET `/invites`, POST `/invites/{id}/respond`, DELETE/PATCH members

**Expenses:** GET/POST `/families/{id}/expenses`, PUT/DELETE `/families/{id}/expenses/{eid}`, POST `/families/{id}/receipts`

**Budget:** GET `/families/{id}/budget/summary?month=YYYY-MM`

**Categories & Goals:** CRUD `/families/{id}/categories`, GET/PUT `/families/{id}/goals`

**Export:** GET `/families/{id}/export?month=YYYY-MM`

**Rate Limiting:**
- `POST /auth/*`: 10/min (IP)
- `POST /*/receipts`: 10/min (User ID)
- `GET /*/export/*`: 5/hour (User ID)
- All other: 120/min (User ID)

### 5.3 Database Schema (10 Tables)

| Table | Key Columns | Notes |
|-------|------------|-------|
| `users` | id, google_id, email, timezone | No password (Google OAuth only) |
| `families` | id, name, timezone, edit_grace_days (default 7), created_by | Family = tenant |
| `family_members` | family_id, user_id, role (admin\|member) | UNIQUE(family_id, user_id) |
| `categories` | family_id, name, is_active, sort_order | Soft-archive via is_active |
| `monthly_goals` | family_id, category_id, year_month, amount_cents, version | Optimistic locking (version) |
| `expenses` | family_id, category_id, user_id, amount_cents, expense_date, year_month, receipt_id, updated_at | Optimistic locking (updated_at) |
| `receipts` | family_id, uploaded_by, image_path, raw_response (JSONB), status, parsed_* | Decoupled from expenses |
| `invites` | family_id, invited_user_id, invited_by, status | Internal users only |
| `refresh_token_blacklist` | jti, user_id, expires_at | Token revocation |
| `audit_log` | user_id, family_id, action, resource_type, ip_address, details (JSONB) | Immutable (REVOKE DELETE) |

**PostgreSQL Extensions:** `pgcrypto` (UUID generation), `pg_trgm` (trigram similarity for category suggestion)

### 5.4 Row-Level Security

**Pattern:** FastAPI middleware sets `SET app.current_user_id = '<uuid>'` before each query.

RLS helper functions (`SECURITY DEFINER STABLE`):
- `user_in_family(family_id)` — checks membership
- `user_is_family_admin(family_id)` — checks admin role

**Policies:**
- Expenses: all members SELECT, own-user INSERT, all members UPDATE
- Categories: all members SELECT, admin-only INSERT/UPDATE
- Goals: all members SELECT, admin-only INSERT/UPDATE
- Audit log: all members SELECT, no UPDATE/DELETE (REVOKE)

### 5.5 Key Design Patterns

**Integer Cents:** All amounts stored as `INTEGER` (e.g., $45.23 → 4523). `CHECK (amount_cents > 0)`. Frontend divides by 100 for display.

**Year_Month Denormalization:** `VARCHAR(7)` (e.g., '2026-03') on expenses eliminates `DATE_TRUNC` in dashboard queries. Index: `(family_id, year_month)`.

**Optimistic Locking:**
- Goals: `version INTEGER` → `WHERE version = ? SET version = version + 1` → 409 on mismatch
- Expenses: `updated_at TIMESTAMPTZ` → `WHERE updated_at = ?` → 409 on mismatch

**Soft Deletes:** Categories archived via `is_active = false`. Expenses use audit log for deletion tracking.

**Edit Grace Period:** `families.edit_grace_days` (default 7). Application enforces: if `NOW() - month_end > grace_days`, past-month expenses are read-only.

**Category Suggestion:** After Claude extracts merchant name, query `expenses.description` with pg_trgm trigram similarity > 0.6 to suggest category. Fallback: family's most-used category.

### Deep-Dive Findings

**Indexes (15 defined):**

| Index | Table | Columns | Type |
|-------|-------|---------|------|
| `idx_expenses_family_month` | expenses | (family_id, year_month) | B-tree |
| `idx_expenses_family_category_month` | expenses | (family_id, category_id, year_month) | B-tree |
| `idx_expenses_description_trgm` | expenses | description | GIN (pg_trgm) |
| `idx_expenses_user` | expenses | (user_id) | B-tree |
| `idx_expenses_date` | expenses | (expense_date) | B-tree |
| `idx_monthly_goals_family_month` | monthly_goals | (family_id, year_month) | B-tree |
| `idx_family_members_family` | family_members | (family_id) | B-tree |
| `idx_family_members_user` | family_members | (user_id) | B-tree |
| `idx_invites_invited_user` | invites | (invited_user_id, status) | B-tree |
| `idx_receipts_family` | receipts | (family_id) | B-tree |
| `idx_receipts_status` | receipts | (status) | B-tree |
| `idx_blacklist_jti` | refresh_token_blacklist | (jti) | B-tree |
| `idx_blacklist_expires` | refresh_token_blacklist | (expires_at) | B-tree |
| `idx_audit_log_family_time` | audit_log | (family_id, timestamp DESC) | B-tree |
| `idx_categories_family` | categories | (family_id) | B-tree |

**Receipt Processing Pipeline:**
1. Client validation: JPEG/PNG/WebP/HEIC, ≤5MB, ≥200×200px
2. Server: magic-byte validation → Pillow re-encoding → save with UUID filename
3. Claude API: tool use with `extract_receipt` schema (forced tool choice)
4. Response handling: success → create expense; partial → fill defaults; not receipt → 422; error → 503

**CSV Export (PRD §15):** UTF-8 with BOM, comma delimiter, CRLF line endings, 7 columns + summary footer with totals. `REPEATABLE READ` isolation for consistent snapshot.

**Environment Variables:**

Backend `.env.example`:
```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/monthly_budget  # pragma: allowlist secret
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=<generate-256-bit-random>
GOOGLE_CLIENT_ID=<from-google-cloud-console>
GOOGLE_CLIENT_SECRET=<from-google-cloud-console>
ANTHROPIC_API_KEY=<from-anthropic-console>
```

Frontend `.env.example`:
```
VITE_API_BASE_URL=http://localhost:8000
```

---

## Success Metrics (Epic 01)

1. `docker compose up` succeeds with all 4 services healthy in <60 seconds
2. `curl http://localhost:8000/api/health` returns 200 with DB/Redis status
3. `curl http://localhost:8000/metrics` returns Prometheus-formatted metrics
4. `cd backend && uv run alembic current` shows initial migration as head
5. `cd backend && uv run pytest` passes (placeholder test)
6. `http://localhost:5173` loads placeholder page showing API health status
7. `cd frontend && npm test` passes (placeholder test)
8. `pre-commit run --all-files` passes with zero errors
9. `make lint && make test` passes locally
10. GitHub Actions CI workflow passes on test PR

---

## Meta-Prompt for /cw-spec

---

Use the following enriched context when generating the specification:

**Feature Name:** Project Scaffolding (Epic 01)

**Problem Statement:** Go from an empty repository to a fully working local development stack where `docker compose up` starts all services (FastAPI backend, React frontend, PostgreSQL, Redis), health checks pass, and both the API and frontend are accessible in a browser.

**Key Components to Define:**
- Backend scaffolding: FastAPI + uv + Alembic async + structlog + Prometheus metrics + health endpoints
- Frontend scaffolding: React 18 + Vite + TypeScript strict + Chakra UI + React Router + TanStack Query
- Docker Compose: 4 services (api, db, redis, frontend) with health checks, security hardening, networking
- Pre-commit + CI: `.pre-commit-config.yaml` as single source of truth, GitHub Actions mirroring, Makefile

**Architectural Constraints:**
- Python 3.12+, uv for deps, async-first (SQLAlchemy 2.0 async + asyncpg)
- React 18+, npm, TypeScript strict mode, Vite with `/api` proxy
- PostgreSQL 16 Alpine, Redis 7 Alpine with auth + maxmemory 128mb
- Docker security: read_only filesystem, cap_drop ALL, non-root user, no-new-privileges
- PostgreSQL needs cap_add: CHOWN, SETUID, SETGID, FOWNER, DAC_READ_SEARCH
- Alembic env.py must use `asyncio.run(run_async_migrations())` pattern
- structlog: JSONRenderer for prod, ConsoleRenderer for dev (switched by ENVIRONMENT env var)

**Patterns to Follow:**
- Pydantic BaseSettings for configuration, loading from env vars / `.env` file
- FastAPI dependency injection for DB sessions (`get_db()`) and auth (`get_current_user()`)
- TanStack Query with `staleTime: 60s`, `refetchOnWindowFocus: true`
- Pre-commit hooks: `language: system` for ruff, `language: python` for mypy/detect-secrets, `language: node` for eslint/prettier/tsc
- detect-secrets with `.secrets.baseline` committed to repo

**Suggested Demoable Units:**
1. Backend Scaffolding — FastAPI + uv + Alembic + structlog + Prometheus + health endpoints
2. Frontend Scaffolding — React + Vite + Chakra UI + Router + TanStack Query + placeholder page
3. Docker Compose & Infrastructure — 4 services, health checks, security hardening, networking
4. Pre-commit, CI & Developer Tooling — `.pre-commit-config.yaml`, GitHub Actions, Makefile, .env.example

**Code References:**
- PRD: `/Users/jburns/git/monthly-budget/PRD.md` (§7.2 tech stack, §8 threat model, §9 auth, §10 schema, §16 secrets, §17 containers, §18 structure)
- Spec: `/Users/jburns/git/monthly-budget/docs/specs/01-spec-project-scaffolding/01-spec-project-scaffolding.md`
- Q&A: `/Users/jburns/git/monthly-budget/docs/specs/01-spec-project-scaffolding/01-questions-1-project-scaffolding.md`

---
