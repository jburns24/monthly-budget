# AGENTS.md

Agent guidance for the monthly-budget monorepo.

## Build & Run Commands

**Primary commands (Taskfile):**
```bash
task install              # Install pre-commit hooks + all deps (parallel)
task up                   # Create k3d cluster if absent + run Tilt (UI at localhost:10350)
task stop                 # Stop Tilt, keep the cluster and its data
task down                 # Stop Tilt + delete the cluster
task lint                 # Run all quality checks (pre-commit)
task test                 # Run all tests (backend + frontend in parallel) — backend half needs the cluster up
task clean                # Clean generated files
```

**Dev cluster (k3d + kustomize + Tilt):**
```bash
task cluster:up           # Create/start the k3d cluster only
task cluster:down         # Delete the cluster and its registry
task cluster:reset        # cluster:down + cluster:up
task k8s:status           # get all,ingress,pvc in the monthly-budget namespace
task k8s:logs -- backend  # Tail a workload (backend|frontend|postgres|redis)
task db:reset             # Delete the postgres StatefulSet+PVC, re-trigger postgres + backend-migrate
```

**Backend (from `backend/` or via namespace):** — `be:test` and the db tasks all require the dev cluster to be up (`task up`).
```bash
task be:test              # pytest via the pg port-forward helper (supports -- -k "test_name")
task be:lint              # Ruff check + format check
task be:format            # Auto-format
task be:db:migrate        # Staleness check, then `alembic upgrade head` IN-CLUSTER
task be:db:downgrade      # `alembic downgrade -1` IN-CLUSTER
task be:db:revision MSG="description"  # Autogenerate on the HOST so the .py lands in git
```

**Frontend (from `frontend/` or via namespace):**
```bash
task fe:test              # Run vitest
task fe:lint              # ESLint
task fe:format            # Prettier
task fe:typecheck         # tsc --noEmit
```

### Backend direct CLI (from `backend/` directory)
`conftest.py` opens a real engine against `settings.database_url` (localhost:5432 per the repo-root `.env`), but Postgres is in-cluster and unpublished — so prefix any bare `pytest` with the port-forward helper, or just use `task be:test`.
```bash
uv sync --all-extras              # Install deps including dev
../scripts/dev/pg_port_forward.sh uv run pytest                    # Run all tests
../scripts/dev/pg_port_forward.sh uv run pytest tests/test_foo.py  # Single test file
../scripts/dev/pg_port_forward.sh uv run pytest -k "test_name"     # Single test by name
uv run ruff check .               # Lint (no DB needed)
uv run ruff format .              # Auto-format (no DB needed)
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
Prefer the tasks — they pick the right side of the cluster boundary for you. Raw equivalents:
```bash
kubectl -n monthly-budget exec deploy/backend -- alembic upgrade head   # Apply (in-cluster)
../scripts/dev/pg_port_forward.sh uv run alembic revision --autogenerate -m "desc"  # Generate (host)
```

## Manual Test Scripts

```bash
uv run python test-scripts/scan_receipt_probe.py [IMAGE]  # From backend/. Runs a receipt through the real pipeline with a LIVE Anthropic call — use when touching receipt scanning, the Claude prompt/tool schema, or category suggestion, since tests/ and the e2e suite all mock AsyncAnthropic. See backend/test-scripts/README.md.
```

## Architecture

**Monorepo** with a FastAPI backend and React frontend. Local dev runs on a k3d
(k3s-in-Docker) cluster: kustomize manifests deployed by Tilt (live-reload), with
Taskfile as the CLI entry point.

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
- **k3d.yaml** — cluster `monthly-budget` (1 server + 1 agent), Traefik ingress published on host :8080, k3d-managed image registry `monthly-budget-registry` (host :5111 / in-cluster :5000)
- **manifests/** — `base/` (namespace, postgres StatefulSet, redis, backend Deployment + migrate Job + receipts PVC, frontend, ingress) and `overlays/dev/` (namespace `monthly-budget`, generated `ConfigMap/app-config` + `Secret/app-secrets`, `disableNameSuffixHash: true`). Render with `kubectl kustomize manifests/overlays/dev`. The base has no ConfigMap/Secret of its own — always build an overlay.
- **Tiltfile** — deploys `manifests/overlays/dev`, builds the `monthly-budget-backend` / `monthly-budget-frontend` images, and live-syncs source into the pods; web UI at localhost:10350. It **hard-fails unless `k8s_context() == 'k3d-monthly-budget'`** — always start via `task up`, never bare `tilt up`.
- Tilt resources are Kubernetes workloads, not `local_resource` processes: `postgres`, `redis`, `backend-migrate` (Job, deleted+recreated each apply), `backend`, `frontend`, and `cluster-config` (namespace/ConfigMap/Secret/ingress/PVC).
- Debug via `kubectl -n monthly-budget <...>`, `task k8s:logs -- <workload>`, or the Tilt UI. There is no `docker compose` in this repo.
- **Taskfile.yml** — root CLI task orchestrator with `backend/Taskfile.yml` and `frontend/Taskfile.yml` includes
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

## Installed Skills

See [.claude/rules/skills.md](.claude/rules/skills.md) for the full skill trigger table and sub-agent guidance (read this file if you need skill-selection details).

## Agent Skills

Prerequisites:
- Docker running locally.
- `gh auth login` once — `scripts/skills-oci.sh` auto-derives `GITHUB_TOKEN` from `gh auth token` for registry pulls/pushes. Override by exporting `GITHUB_TOKEN` yourself (e.g. in CI via `secrets.GITHUB_TOKEN`).
- Non-interactive use (agents, scripts, CI): pass `--plain` explicitly, e.g. `task skills:add -- --plain ghcr.io/jburns24/skills/<name>:<tag>`. Only `skills:install` defaults to `--plain` today; `skills:add`, `skills:remove`, and raw `skills` will try to open a TTY and crash without it.
- Known limitation: `task skills -- verify` currently fails with `cosign not found in PATH` (a gap in the upstream `skills-oci` image, not fixable from this repo) — skip verification for now.
- Tip: tags aren't recorded in the upstream `jburns24/skills` `catalog.yaml`; find a skill's published version with `gh api "/user/packages/container/skills%2F<name>/versions" --jq '.[].metadata.container.tags'`.

Manage Agent Skills in this repo with these tasks (args after `--` pass to the CLI):
```bash
task skills:add -- ghcr.io/jburns24/skills/<name>:<tag>  # install a skill from a registry
task skills:remove -- --name <name>                      # remove an installed skill
task skills:install                                      # install everything in skills.json
task skills:register                                     # add the SessionStart auto-install hook
```

For anything else, run `task skills -- --help`.

## Dev environment

- Start: `task up` · pause: `task stop` (keeps data) · destroy: `task down`
- Cluster `k3d-monthly-budget`, namespace `monthly-budget`, Tilt UI http://localhost:10350
- **App + API: http://localhost:8080** (Traefik ingress). `/api`, `/docs`, `/redoc`, `/openapi.json`, `/metrics` → backend:8000; `/` catch-all → frontend:5173. App and API share one origin, so the frontend's relative `/api/...` requests are same-origin. The frontend Deployment sets `VITE_HMR_CLIENT_PORT=8080`, so Vite advertises its HMR websocket on :8080 whichever URL you browse.
- Tilt also port-forwards `5173` (frontend pod) and `8000` (backend pod) for direct/single-service access — the Playwright config targets those.
- Postgres/Redis are not published to the host; in-cluster they are `postgres:5432` / `redis:6379`.
- Postgres data lives in a PVC inside the cluster. It survives `task stop`; `task down` and `task cluster:reset` destroy it.

### Config and secrets

In-cluster env comes from `manifests/overlays/dev/config/` — `app-config.env` → `ConfigMap/app-config`, `app-secrets.env` → `Secret/app-secrets`, both consumed wholesale via `envFrom`. Every value is a throwaway local-only placeholder, not a real credential. `ANTHROPIC_MOCK=true` is set there, which is why the e2e receipt specs are deterministic and no Anthropic key is needed.

kustomize does **not** strip trailing comments from env files (`FOO=bar # x` yields the literal `bar # x`) — keep comments on their own line. `app-secrets.env` trips detect-secrets; re-baseline rather than adding inline pragmas.

The repo-root `.env` is separate: it feeds `Taskfile.yml` (`dotenv:`) and the Tiltfile (`dotenv()`), i.e. the tooling, not the cluster. `backend/.env` and `frontend/.env` only matter for host-native runs.

### Common failure modes

- `tilt up` aborts with a context error → kube context isn't `k3d-monthly-budget`. Use `task up`.
- `ImagePullBackOff` → the registry's two names/two ports (`localhost:5111` for pushes, `monthly-budget-registry:5000` for in-cluster pulls) disagree between `k3d.yaml` and `default_registry()` in the Tiltfile. Read the comment blocks in both before touching either.
- http://localhost:8080 404s on a fresh cluster → Traefik is installed via a HelmChart CR and isn't ready yet. `kubectl -n kube-system rollout status deploy/traefik`.

### Migrations across the cluster boundary

Postgres is an unpublished StatefulSet, which splits the alembic tasks by whether they write files:

- **In-cluster** (`kubectl exec deploy/backend`): `be:db:migrate`, `be:db:downgrade`. They only mutate the DB, and the pod already has the URL and creds. Both go through an internal `_require-backend` guard that errors with "the dev environment has to be up first: task up" when there's no `deploy/backend`, and otherwise waits on `rollout status` (up to 180s).
- **On the host** (via `scripts/dev/pg_port_forward.sh`): `be:db:revision`, `be:test`. `revision --autogenerate` **writes a `.py` file** — run it in-cluster and the file lands in the pod's overlayfs, where `live_update` (host→container only) never copies it back and the next rebuild discards it. Autogenerate also needs the DB already at head, so run `be:db:migrate` first.

`pg_port_forward.sh` gives host commands `localhost:5432` via a temporary `kubectl port-forward` for the life of the command. **Gotcha:** if something already listens on 5432 it reuses it *without checking what it is* — a local Postgres.app/Homebrew install wins and you silently work against the wrong database. It prints a notice; `DEV_DB_PORT` overrides.

### Stale database migrations

Switching branches with divergent Alembic histories leaves `alembic_version` pointing at a revision absent from `backend/alembic/versions/`, and bare `alembic upgrade` then dies with an unhelpful `Can't locate revision identified by '<hash>'`. `scripts/dev/ensure_dev_db.sh` runs first in `be:db:migrate` and catches it.

It is **detect-only** — it never destroys anything; `task db:reset` owns the destructive side. On a stale DB it exits 1 and tells you to run `task db:reset`. A missing or not-ready Postgres pod, or an empty `alembic_version`, all exit 0.

### Resetting the database

`task db:reset` deletes the postgres StatefulSet and its PVC, then `tilt trigger postgres` + `tilt trigger backend-migrate`. Tilt must be running. Local dev data is intentionally disposable.
