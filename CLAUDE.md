# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

**Primary commands (Taskfile):**
```bash
task install              # Install pre-commit hooks + all deps (parallel)
task up                   # Start Tilt (all services + web UI at localhost:10350)
task down                 # Stop Tilt
task lint                 # Run all quality checks (pre-commit)
task test                 # Run all tests (backend + frontend in parallel)
task clean                # Clean generated files
```

**Backend (from `backend/` or via namespace):**
```bash
task be:test              # Run backend tests (supports -- -k "test_name")
task be:lint              # Ruff check + format check
task be:format            # Auto-format
task be:db:migrate        # Alembic upgrade head
task be:db:revision MSG="description"  # Generate migration
```

**Frontend (from `frontend/` or via namespace):**
```bash
task fe:test              # Run vitest
task fe:lint              # ESLint
task fe:format            # Prettier
task fe:typecheck         # tsc --noEmit
```

### Backend direct CLI (from `backend/` directory)
```bash
uv sync --all-extras              # Install deps including dev
uv run pytest                     # Run all tests
uv run pytest tests/test_foo.py   # Run a single test file
uv run pytest -k "test_name"      # Run a single test by name
uv run ruff check .               # Lint
uv run ruff format .              # Auto-format
```

### Frontend direct CLI (from `frontend/` directory)
```bash
npm install                       # Install deps
npm run test:run                  # Run all tests (vitest, single run)
npm test                          # Run tests in watch mode
npm run lint                      # ESLint
npm run format                    # Prettier auto-format
npm run format:check              # Prettier check only
npx tsc --noEmit                  # Type check
```

### Database Migrations (from `backend/` directory)
```bash
uv run alembic upgrade head                    # Apply all migrations
uv run alembic revision --autogenerate -m "desc"  # Generate migration from model changes
```

## Architecture

**Monorepo** with a FastAPI backend and React frontend, orchestrated via Docker Compose + Tilt (live-reload dev environment) + Taskfile (CLI command orchestration).

### Backend (`backend/`)
- **FastAPI** with async SQLAlchemy 2.0 + asyncpg (PostgreSQL) and Redis
- Entry point: `app/main.py` — creates the FastAPI app with lifespan handler, Prometheus instrumentation
- Config: `app/config.py` — pydantic-settings `Settings` class, loads from env vars / `.env` file
- Database: `app/database.py` — async engine, session factory (`AsyncSessionLocal`), `Base` declarative base, `get_db()` dependency
- Migrations: `alembic/` — async Alembic setup, `env.py` reads `database_url` from app config
- Structured logging via `structlog` (`app/logging.py`)
- Layout: `app/routers/`, `app/models/`, `app/schemas/`, `app/services/` (mostly stubs currently)
- Tests: `tests/` — pytest with `asyncio_mode = "auto"`, uses httpx for async test client

### Frontend (`frontend/`)
- **React 19** + TypeScript + Vite
- UI: Chakra UI v3 + Emotion + Framer Motion
- Routing: react-router-dom v7
- Data fetching: TanStack React Query
- Testing: Vitest + Testing Library + happy-dom/jsdom

### Infrastructure
- **Tiltfile** — container orchestration with live_update, web UI dashboard at localhost:10350
- **Taskfile.yml** — root CLI task orchestrator with `backend/Taskfile.yml` and `frontend/Taskfile.yml` includes
- Docker Compose services: `api` (FastAPI), `db` (Postgres 16), `redis` (Redis 7), `frontend` (Vite dev server)
- All containers have security hardening: read-only fs, no-new-privileges, dropped capabilities, resource limits
- CI: GitHub Actions (`.github/workflows/ci.yml`) runs on PRs to `main` — pre-commit checks, backend tests (with Postgres service), frontend tests

## Code Quality

Pre-commit hooks (`.pre-commit-config.yaml`) are the single source of truth for all checks. CI runs the same hooks.

- **Python**: ruff (lint + format, line-length=120, target py312), mypy (--ignore-missing-imports)
- **TypeScript**: ESLint, Prettier, tsc --noEmit
- **Security**: detect-secrets with `.secrets.baseline`

## Key Conventions

- Python package manager is **uv** (not pip). Always use `uv run` to execute Python tools.
- Backend uses **async throughout** — async routes, async SQLAlchemy sessions, async tests.
- Alembic is configured for async via `async_engine_from_config` in `env.py`. Models must be imported into `app/database.py` `Base` for autogenerate to detect them.
- The main branch is `main`. PRs target `main`.
