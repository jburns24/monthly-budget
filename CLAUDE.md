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

**Monorepo** with a FastAPI backend and React frontend, orchestrated via Tilt (live-reload dev environment) + Taskfile (CLI command orchestration).

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
- **Tiltfile** — orchestrates all services as `local_resource` processes with hot-reload; web UI at localhost:10350. Debug service issues via `tilt logs <service>` or the Tilt UI — do NOT use `docker compose` commands.
- **Taskfile.yml** — root CLI task orchestrator with `backend/Taskfile.yml` and `frontend/Taskfile.yml` includes
- Services: `api` (FastAPI on :8000), `db` (Postgres 16 on :5432 via `docker run`), `redis` (Redis 7 on :6379 via `docker run`), `frontend` (Vite dev server on :5173)
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

## Installed Skills — When to Use Them

These skills are installed in this environment. Use them (via the `Skill` tool) when working in the relevant areas. When spawning sub-agents, include the applicable skill names in the agent prompt so they know to invoke them too.

### Anytime
| Trigger | Skill |
|---|---|
| Before implementing any feature or bugfix | `test-driven-development` |
| Encountering a bug, test failure, or unexpected behavior | `systematic-debugging` |
| After making changes — review for quality/simplicity | `simplify` |
| Local code review before committing | `local_review` |

### Backend (`backend/` — FastAPI, SQLAlchemy, Python)
| Trigger | Skill |
|---|---|
| Building new FastAPI endpoints or service patterns | `fastapi-templates` |
| Designing or refactoring backend architecture | `architecture-patterns` |
| Optimizing slow Python code or investigating memory issues | `python-performance-optimization` |

### Frontend (`frontend/` — React, TypeScript, Chakra UI)
| Trigger | Skill |
|---|---|
| Writing or reviewing React components | `vercel-react-best-practices` |
| Refactoring components (boolean prop proliferation, composition) | `vercel-composition-patterns` |
| Building new UI screens or visual components | `frontend-design` |
| Working with complex TypeScript types or generics | `typescript-advanced-types` |
| Auditing UI for accessibility or design guidelines | `web-design-guidelines` |
| Writing or running Playwright / E2E tests | `webapp-testing` |

### Infrastructure
| Trigger | Skill |
|---|---|
| Modifying `Tiltfile` or debugging dev service issues | `tilt-dev` |

### Feature Development Workflow (non-trivial features)
Use these in order for significant new features:
1. `claude-workflow:cw-spec` — write a structured spec
2. `claude-workflow:cw-plan` — break spec into a task graph
3. `claude-workflow:cw-execute` — implement each task
4. `claude-workflow:cw-review` — review implementation
5. `claude-workflow:cw-validate` — validate against spec

### Passing Skills to Sub-Agents
When spawning an agent via the `Agent` tool for work in any of the above areas, include a line in the prompt such as:

> "This project uses installed skills. For backend work invoke `fastapi-templates` and `test-driven-development` via the Skill tool before writing implementation code. For frontend work invoke `vercel-react-best-practices`. For any bug use `systematic-debugging` first."

Tailor the list to the area the sub-agent is working in.
