# 01-spec-project-scaffolding

## Introduction/Overview

This epic establishes the foundational project structure, development environment, and infrastructure for the Monthly Budget application. The goal is to go from an empty repository to a fully working local development stack where `docker compose up` starts all services (FastAPI backend, React frontend, PostgreSQL, Redis), health checks pass, and both the API and frontend are accessible in a browser. This foundation enables all subsequent epics to build features on a proven, running stack.

## Goals

- Scaffold the full project directory structure matching the PRD's architecture (§18)
- Configure Docker Compose with all four services (API, PostgreSQL, Redis, frontend) with health checks and proper networking
- Set up the FastAPI backend with uv, structured logging (structlog), and Prometheus metrics
- Set up the React frontend with Vite, TypeScript, Chakra UI, React Router, and TanStack Query
- Configure Alembic for database migrations (empty initial migration)
- Set up pre-commit framework as the single source of truth for all code quality checks (linting, formatting, type-checking)
- Set up GitHub Actions CI pipeline that runs `pre-commit run --all-files` to enforce the same checks as local development
- Provide `.env.example` files with all secrets the full application will eventually need

## User Stories

**As a developer (Jake persona)**, I want to clone the repo, run `docker compose up`, and have all services start with passing health checks so that I can immediately begin building features.

**As a developer**, I want structured logging and a Prometheus metrics endpoint from day one so that I have observability baked in rather than bolted on.

**As a contributor**, I want pre-commit hooks to catch linting, formatting, and type errors before code leaves my machine so that CI failures are rare and feedback is immediate.

**As a contributor**, I want CI to run the same pre-commit checks so that nothing slips through even if hooks are bypassed.

## Demoable Units of Work

### Unit 1: Backend Scaffolding (FastAPI + uv + Alembic)

**Purpose:** Establish the Python backend project structure with dependency management, database migration tooling, structured logging, and metrics — ready to accept feature code in subsequent epics.

**Functional Requirements:**
- The backend shall use Python 3.12+ with uv for dependency management and a `pyproject.toml` at `backend/pyproject.toml`
- The backend shall use FastAPI as the web framework, served by Gunicorn with Uvicorn workers
- The backend shall configure Alembic for async PostgreSQL migrations with an empty initial migration (no tables) in `backend/alembic/`
- The backend shall use SQLAlchemy 2.0 (async) with asyncpg as the database driver, configured in `backend/app/database.py`
- The backend shall use structlog for structured JSON logging configured in `backend/app/logging.py`
- The backend shall expose a Prometheus-compatible metrics endpoint at `GET /metrics` using `prometheus-fastapi-instrumentator` or equivalent
- The backend shall expose `GET /api/health` returning `{"status": "healthy", "database": "connected", "redis": "connected"}` (200) when all dependencies are reachable, or appropriate degraded status (503) when any dependency is unreachable
- The backend shall expose `GET /api/health/ready` returning 200 only when migrations are current
- The backend shall use Pydantic `BaseSettings` for configuration in `backend/app/config.py`, loading from environment variables
- The backend shall include `ruff` for linting and formatting, configured in `pyproject.toml`
- The backend shall include `pytest` with `pytest-asyncio` and `httpx` (AsyncClient) for testing, with a passing placeholder test

**Proof Artifacts:**
- CLI: `curl http://localhost:8000/api/health` returns 200 with JSON status — demonstrates backend is running and connected to DB/Redis
- CLI: `curl http://localhost:8000/metrics` returns Prometheus-formatted metrics — demonstrates observability is wired up
- CLI: `cd backend && uv run alembic current` shows the initial migration as head — demonstrates migration tooling works
- Test: `cd backend && uv run pytest` passes — demonstrates test infrastructure works

### Unit 2: Frontend Scaffolding (React + Vite + Chakra UI)

**Purpose:** Establish the React frontend project structure with all core libraries wired up and a placeholder page — ready to accept UI components in subsequent epics.

**Functional Requirements:**
- The frontend shall use React 18+ with TypeScript in strict mode, scaffolded with Vite in `frontend/`
- The frontend shall use npm as the package manager
- The frontend shall install and configure Chakra UI as the component library with a custom theme provider in `frontend/src/theme.ts`
- The frontend shall install and configure React Router (v6+) with a placeholder route at `/` in `frontend/src/App.tsx`
- The frontend shall install and configure TanStack Query (React Query) with a `QueryClientProvider` wrapping the app
- The frontend shall display a placeholder page at `/` showing "Monthly Budget" and a confirmation that the app is running (e.g., "Frontend is running. API health: [status]") by fetching `/api/health` from the backend
- The frontend shall configure Vite to proxy `/api` requests to the backend at `http://localhost:8000` during development
- The frontend shall include `prettier` and `eslint` configured in the project root for consistent formatting and linting
- The frontend shall include Vitest with React Testing Library, with a passing placeholder test
- The frontend shall include a `tsconfig.json` with strict mode enabled and path aliases configured (e.g., `@/` → `src/`)

**Proof Artifacts:**
- Browser: `http://localhost:5173` loads the placeholder page — demonstrates frontend is running
- Browser: Placeholder page shows API health status fetched from backend — demonstrates frontend-to-backend connectivity
- Test: `cd frontend && npm test` passes — demonstrates frontend test infrastructure works

### Unit 3: Docker Compose & Infrastructure

**Purpose:** Wire all services together with Docker Compose so that a single `docker compose up` command starts the full stack with health checks, proper networking, and volume persistence.

**Functional Requirements:**
- Docker Compose shall define four services: `api`, `db` (PostgreSQL 16 Alpine), `redis` (Redis 7 Alpine), and `frontend`
- The `api` service shall build from `backend/Dockerfile` using a multi-stage build (builder + runtime) running as a non-root user
- The `api` service shall depend on `db` and `redis` with `condition: service_healthy`
- The `api` service shall run Alembic migrations on startup before starting the application server
- The `db` service shall use a named volume (`pg_data`) for data persistence and include a health check using `pg_isready`
- The `redis` service shall require authentication via password from environment, include a health check using `redis-cli ping`, and set `maxmemory 128mb`
- The `frontend` service shall build from `frontend/Dockerfile` (Node-based dev server) or run via a simple Node image with volume mounts for hot-reload during development
- All services shall be on a shared Docker network for inter-service communication
- The `api` container shall use `read_only: true` filesystem with tmpfs for `/tmp`, `security_opt: no-new-privileges`, and `cap_drop: ALL` per PRD §17
- The `db` and `redis` containers shall follow the hardening patterns from PRD §17 (read-only filesystem, cap_drop, security_opt)
- A `docker-compose.yml` at the project root shall be the single entry point for local development

**Proof Artifacts:**
- CLI: `docker compose up` starts all four services with no errors — demonstrates full stack runs
- CLI: `docker compose ps` shows all services as "healthy" — demonstrates health checks pass
- CLI: `docker compose down && docker compose up` restarts cleanly with data persisted in volumes — demonstrates persistence works

### Unit 4: Pre-commit, CI Pipeline & Developer Tooling

**Purpose:** Establish pre-commit as the single source of truth for code quality checks, with CI calling the same pre-commit configuration to guarantee local and CI checks are always identical.

**Functional Requirements:**
- A `.pre-commit-config.yaml` at the project root shall define all code quality hooks as the single source of truth for checks
- Pre-commit hooks shall include: `ruff check` and `ruff format --check` for backend Python linting/formatting
- Pre-commit hooks shall include: `mypy` or `pyright` for backend type checking
- Pre-commit hooks shall include: `eslint` for frontend linting
- Pre-commit hooks shall include: `prettier --check` for frontend formatting
- Pre-commit hooks shall include: `tsc --noEmit` for frontend type checking
- Pre-commit hooks shall include standard hooks: `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`, `detect-secrets` (per PRD §16 secret management rules)
- Running `pre-commit install` shall register the hooks so they run automatically on `git commit`
- Running `pre-commit run --all-files` shall execute all checks against the entire codebase
- A GitHub Actions workflow at `.github/workflows/ci.yml` shall run on pull requests to `main`
- The CI pipeline shall run `pre-commit run --all-files` to execute the same lint/format/type checks as local development — no separate lint/format steps
- The CI pipeline shall run backend tests (`pytest`) against a PostgreSQL service container (tests are not part of pre-commit since they require a database)
- The CI pipeline shall run frontend tests (`vitest run`) (tests are not part of pre-commit since they may be slow)
- The CI pipeline shall use the `pre-commit/action` GitHub Action (or equivalent) with caching for pre-commit environments
- The CI pipeline shall use caching for uv dependencies and npm dependencies to minimize test run time
- A `Makefile` or equivalent at the project root shall provide convenience commands: `make lint` (runs `pre-commit run --all-files`), `make test`, `make up`, `make down`
- A `backend/.env.example` shall include all secrets with placeholder values: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ANTHROPIC_API_KEY`
- A `frontend/.env.example` shall include `VITE_API_BASE_URL=http://localhost:8000`
- A `README.md` at the project root shall include quickstart instructions (prerequisites, clone, `pre-commit install`, `docker compose up`, verify health)

**Proof Artifacts:**
- CLI: `pre-commit run --all-files` passes — demonstrates all quality checks pass locally
- CLI: `make lint && make test` passes locally — demonstrates developer tooling works
- Screenshot: GitHub Actions CI workflow passes on a test PR — demonstrates CI runs the same pre-commit checks

## Non-Goals (Out of Scope)

1. **No application features** — no authentication, expense entry, or any business logic. This epic is purely infrastructure
2. **No Caddy reverse proxy** — direct port access in development; Caddy will be added in a deployment/production epic
3. **No database tables** — Alembic is set up with an empty migration; tables are added by feature epics
4. **No PWA configuration** — service workers, manifest, and offline support come in Epic 09
5. **No Kubernetes manifests** — K8s deployment is a separate concern beyond MVP epics
6. **No production Docker Compose** — only `docker-compose.yml` for local development

## Design Considerations

No specific design requirements for this epic. The placeholder frontend page should use Chakra UI's default theme to confirm the library is working, but no design polish is needed.

## Repository Standards

This epic **establishes** the repository standards that all subsequent epics must follow:

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, uv for deps, ruff for lint/format, pytest for tests
- **Frontend:** React 18+, TypeScript strict, Vite, Chakra UI, React Router v6, TanStack Query, npm, prettier + eslint, Vitest + React Testing Library
- **Git:** Feature branches off `main`. Squash merge. Conventional commits (e.g., `feat:`, `fix:`, `chore:`). Pre-commit hooks installed via `pre-commit install`
- **Code quality:** All lint/format/type checks defined in `.pre-commit-config.yaml` — this is the single source of truth. CI runs `pre-commit run --all-files` to guarantee parity with local checks
- **Project layout:** Follows the structure defined in PRD §18
- **Docker:** Multi-stage builds, non-root users, security hardening (read-only fs, cap_drop, no-new-privileges)
- **Migrations:** Alembic with async PostgreSQL. One migration per feature branch
- **Config:** Pydantic BaseSettings, environment variables, `.env` files (gitignored)
- **Logging:** structlog with JSON output
- **API docs:** Auto-generated OpenAPI at `/docs`

## Technical Considerations

- **uv** is used instead of pip/poetry for Python dependency management — requires uv to be installed in the Docker build stage and developer machines
- **Alembic async** configuration requires `asyncpg` and the async engine from SQLAlchemy — the `env.py` must use `run_async_migrations` pattern
- **Docker Compose health checks** should use `test`, `interval`, `timeout`, `retries`, and `start_period` fields to handle slow startup
- **Vite proxy** must be configured in `vite.config.ts` to forward `/api` requests to the backend to avoid CORS issues during development
- **structlog** should be configured with `ProcessorPipeline` including `JSONRenderer` for production and `ConsoleRenderer` for local development (based on an environment variable)
- **Prometheus metrics** via `prometheus-fastapi-instrumentator` auto-instruments all endpoints; the `/metrics` endpoint should be excluded from auth in later epics
- **pre-commit** requires Python to be installed on the developer's machine (separate from the Docker environment). The `.pre-commit-config.yaml` should use `language: system` for hooks that call project-local tools (ruff, eslint, etc.) where possible, or `language: node`/`language: python` with pinned versions for standalone hooks
- **detect-secrets** hook should use `language: python` with a `.secrets.baseline` file committed to the repo

## Security Considerations

- `.env` files are gitignored (already configured in `.gitignore`)
- `.env.example` files contain only placeholder values, never real secrets
- Docker containers run as non-root users with minimal capabilities
- PostgreSQL password is set via environment variable in Docker Compose (loaded from `.env`)
- Redis requires authentication via password
- No secrets are embedded in Docker images (multi-stage build, no COPY of `.env`)
- The `secrets/` directory is gitignored for Docker Compose secrets (used in later epics)

## Success Metrics

1. **`docker compose up` succeeds** with all 4 services healthy in under 60 seconds on a fresh build
2. **`/api/health` returns 200** with database and Redis status confirmed
3. **Frontend loads** in browser and displays API health status
4. **CI pipeline passes** on a PR with the scaffolding code
5. **`pre-commit run --all-files`** passes locally with zero errors
6. **`make test`** passes locally with zero errors

## Open Questions

1. Should the frontend Dockerfile use a multi-stage build for production (Node build → nginx serve), or is a simple Node dev server image sufficient for now? — *Answer: dev server only for now; production Dockerfile comes with the deployment epic.*
2. Should we pin exact dependency versions in `pyproject.toml` and `package.json`, or use ranges? — *Answer: use ranges with lockfiles (uv.lock, package-lock.json) for reproducibility.*
