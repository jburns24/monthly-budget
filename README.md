# Monthly Budget

A full-stack budget management application with FastAPI backend and React frontend.

## Prerequisites

- **Docker** (running — k3d creates the cluster as Docker containers)
- **Python** 3.12 or later
- **Node.js** 20 or later
- **uv** (Python package manager) - [install uv](https://docs.astral.sh/uv/getting-started/installation/)
- **pre-commit** - `pip install pre-commit` or `brew install pre-commit`
- **k3d** (local Kubernetes cluster) - `brew install k3d`
- **kubectl** (Kubernetes CLI) - `brew install kubectl`
- **Tilt** (dev environment orchestration) - `brew install tilt-dev/tap/tilt`
- **Task** (task runner) - `brew install go-task/tap/task`

## Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd monthly-budget
```

### 2. Copy Environment Files

```bash
# Repo-root environment (read by Task and Tilt themselves)
cp .env.example .env

# Backend environment configuration
cp backend/.env.example backend/.env

# Frontend environment configuration
cp frontend/.env.example frontend/.env
```

Edit the `.env` files with your actual configuration values:
- **.env**: loaded by `Taskfile.yml` (`dotenv:`) and by the `Tiltfile` (`dotenv()`), so it configures the tooling — not the cluster
- **backend/.env**: used when you run the backend directly on your machine (`uv run pytest`, `uv run alembic ...`)
- **frontend/.env**: used when you run Vite directly on your machine (`npm run dev`)

The services **inside** the dev cluster do not read any of these. Their environment
comes from `manifests/overlays/dev/config/`:

- `app-config.env` → generated `ConfigMap/app-config` (non-secret settings, including `ANTHROPIC_MOCK=true`, which is why receipt scanning is deterministic locally and needs no Anthropic key)
- `app-secrets.env` → generated `Secret/app-secrets` (`DATABASE_URL`, `REDIS_URL`, JWT/session secrets)

Every value in those two files is a throwaway placeholder for a local-only k3d
cluster. Do not treat them as real credentials, and do not reuse them anywhere.

### 3. Install Dependencies and Pre-commit Hooks

```bash
task install
```

This will (in parallel):
- Install backend dependencies via uv
- Install frontend dependencies via npm
- Install pre-commit hooks for git

### 4. Start Services

```bash
task up
```

This creates the local k3d cluster `monthly-budget` (if it doesn't exist
already), switches your kubectl context to `k3d-monthly-budget`, waits for the
Traefik ingress controller, and then runs `tilt up`. Tilt applies
`manifests/overlays/dev` into the `monthly-budget` namespace and live-syncs your
source into the running pods.

Workloads: `postgres`, `redis`, `backend-migrate` (Alembic Job), `backend`,
`frontend`, plus a `cluster-config` group for the namespace, ConfigMap, Secret,
ingress, and receipts PVC.

**Use http://localhost:8080 — that is the app.** It is the Traefik ingress:
`/api`, `/docs`, `/redoc`, `/openapi.json`, and `/metrics` route to the backend,
and everything else falls through to the Vite dev server. That means the app and
the API share a single origin, so the frontend's relative `/api/...` requests are
same-origin. The frontend Deployment also sets `VITE_HMR_CLIENT_PORT=8080`, so
Vite advertises its HMR websocket on port 8080 regardless of which URL you
browse.

| URL | What it is |
| --- | --- |
| http://localhost:8080 | **Primary.** App + API through the Traefik ingress |
| http://localhost:10350 | Tilt dashboard |
| http://localhost:5173 | Direct port-forward to the frontend pod |
| http://localhost:8000 | Direct port-forward to the backend pod |

The 5173 and 8000 port-forwards are set up by Tilt (`k8s_resource(...,
port_forwards=...)`) for tooling that has to talk to a single service — the
Playwright suite uses them, for instance. Prefer 8080 for browsing.

Postgres and Redis are **not** published to the host. Reach them in-cluster as
`postgres:5432` / `redis:6379`, or forward them yourself:

```bash
kubectl -n monthly-budget port-forward svc/postgres 5432:5432
```

### 5. Verify Health

Check that the backend is running:

```bash
curl http://localhost:8080/api/health
```

Open http://localhost:8080 in your browser to view the frontend.

## Common Commands

### Run Quality Checks

```bash
task lint
```

Runs all code quality checks:
- ruff (Python linting and formatting)
- mypy (type checking)
- eslint (JavaScript/TypeScript linting)
- prettier (code formatting)
- detect-secrets (security baseline)

### Run Tests

```bash
task test
```

Runs backend + frontend tests in parallel.

The backend suite connects to a real Postgres, which now lives in the cluster, so
**`task up` has to have been run first.** `task be:test` opens a temporary
`kubectl port-forward` for the duration of the run (via
`scripts/dev/pg_port_forward.sh`) to put the database on `localhost:5432`. The
frontend suite has no such dependency.

### Backend Commands

```bash
task be:test                         # Run backend tests (needs the cluster up)
task be:lint                         # Ruff check + format check
task be:format                       # Auto-format
task be:db:migrate                   # Apply migrations — runs alembic inside the cluster
task be:db:downgrade                 # Downgrade one revision, also inside the cluster
task be:db:revision MSG="add users"  # Generate a migration — runs on your machine
```

The alembic tasks split along one line: `upgrade`/`downgrade` only change the
database, so they run in the backend pod (`kubectl exec`). `revision
--autogenerate` *writes a new `.py` file*, so it has to run on your machine —
a file created inside the pod would be invisible to git and thrown away on the
next rebuild. Autogenerate also diffs your models against the live schema, so
apply migrations before generating one.

All three need the dev environment up. `migrate`/`downgrade` fail with a message
telling you to run `task up` if the backend workload isn't deployed.

### Frontend Commands

```bash
task fe:test              # Run frontend tests
task fe:lint              # ESLint
task fe:format            # Prettier
task fe:typecheck         # TypeScript type checking
task fe:build             # Build for production
```

### Dev Environment Lifecycle

```bash
task up             # Create the cluster if needed, then run Tilt
task stop           # Stop Tilt, leave the cluster and its data alone
task down           # Stop Tilt and delete the cluster (data is gone)

task cluster:up     # Create/start the k3d cluster only, no Tilt
task cluster:down   # Delete the cluster and its registry
task cluster:reset  # cluster:down + cluster:up
```

Use `task stop` for day-to-day pauses — Postgres data lives in a PersistentVolume
inside the cluster and survives it. `task down` and `task cluster:reset` destroy
that volume.

### Inspect the Dev Cluster

```bash
task k8s:status              # Everything in the monthly-budget namespace
task k8s:logs -- backend     # Tail a workload's logs (backend, frontend, postgres, redis)
task db:reset                # Wipe the Postgres volume and re-run migrations (Tilt must be running)
```

Anything these don't cover, reach for `kubectl -n monthly-budget ...` or the Tilt
dashboard.

### Clean Generated Files

```bash
task clean
```

Removes:
- Python cache directories (__pycache__, .pytest_cache, .ruff_cache)
- Frontend node_modules and dist

### List All Available Tasks

```bash
task --list
```

## Project Structure

```
monthly-budget/
├── backend/                  # FastAPI application
│   ├── app/                  # Application source code
│   ├── alembic/              # Database migrations
│   ├── tests/                # Backend tests
│   ├── Dockerfile            # Backend container image
│   ├── Taskfile.yml          # Backend task definitions
│   └── pyproject.toml        # Python dependencies and config
├── frontend/                 # React application
│   ├── src/                  # Source code
│   ├── public/               # Static assets
│   ├── Dockerfile            # Frontend container image
│   ├── Taskfile.yml          # Frontend task definitions
│   └── package.json          # JavaScript dependencies
├── manifests/                # Kubernetes manifests (kustomize)
│   ├── base/                 # postgres, redis, backend, frontend, ingress
│   └── overlays/dev/         # Local dev overlay + generated ConfigMap/Secret
├── k3d.yaml                  # Local k3d cluster + image registry definition
├── Tiltfile                  # Deploys the dev overlay, builds images, live-reload
└── Taskfile.yml              # Root task orchestrator
```

## Development Workflow

1. **Start the dev environment**: `task up`
2. **Make code changes** in backend/ or frontend/ — Tilt syncs them into the running pods and they live-reload automatically. Changing `pyproject.toml`/`uv.lock` or `package.json`/`package-lock.json` rebuilds the image instead; changing `vite.config.ts` needs a manual restart of the `frontend` resource from the Tilt UI.
3. **Pre-commit hooks run automatically** before each commit
4. **Run tests locally**: `task test` (the backend half needs the dev cluster up)
5. **Run quality checks**: `task lint`
6. **Commit your changes** when tests and lint pass

Use the Tilt dashboard at http://localhost:10350 to monitor services, view logs, and run actions (migrate, test, lint) via UI buttons.

For more details on code quality standards, see `.pre-commit-config.yaml`.

## Troubleshooting

### Port Already in Use

The host ports this setup claims are 8080 (ingress), 10350 (Tilt), 5111 (image
registry), and 5173/8000 (Tilt port-forwards):

```bash
# Find what's using a port (example: port 8080)
lsof -i :8080

# Stop everything and try again
task stop
task up
```

### `tilt up` Refuses to Start

The Tiltfile hard-fails unless your kube context is `k3d-monthly-budget`, so it
can never deploy dev manifests to a real cluster by accident. Run `task up`
rather than `tilt up` — it creates the cluster and switches context for you. To
fix the context by hand: `kubectl config use-context k3d-monthly-budget`.

### Pods Stuck in `ImagePullBackOff`

Almost always the local image registry. It answers to two different
name/port pairs — `localhost:5111` for pushes from your machine,
`monthly-budget-registry:5000` for pulls from inside the cluster — and both are
declared, once in `k3d.yaml` and once in the Tiltfile's `default_registry()`.
They have to agree. Read the comment blocks at the top of both files before
changing either. A `task cluster:reset` clears up a registry that got into a bad
state.

### Backend Tests Hit the Wrong Database

`task be:test` and `task be:db:revision` reuse whatever is already listening on
`localhost:5432` instead of port-forwarding the cluster, and they do **not** check
what that listener is. If you have a local Postgres.app or Homebrew Postgres
running, it wins and you'll silently work against the wrong database. The helper
prints a notice when this happens. Either stop the local instance, or point the
helper elsewhere:

```bash
DEV_DB_PORT=15432 task be:test
```

### "The dev database is on migration revision(s) that this branch does not have"

You switched branches and the database is still on an Alembic revision that
doesn't exist in `backend/alembic/versions/` here. `task be:db:migrate` detects
this up front rather than letting alembic fail cryptically. Wipe and re-migrate
(local data is lost):

```bash
task db:reset
```

### Pre-commit Hook Failures

If a pre-commit hook fails:

```bash
# Fix the issues (lint/format)
task be:format
task fe:format
```

Then commit again.

### http://localhost:8080 Returns 404

Usually the ingress controller hasn't finished coming up. k3s installs Traefik
via a HelmChart resource, so the Deployment doesn't exist for the first several
seconds of a new cluster. `task cluster:up` waits for that rollout; a cluster
created by hand with `k3d cluster create` does not. Check it and retry:

```bash
kubectl -n kube-system rollout status deploy/traefik
```

A 404 on a cluster that has been up for a while means the `frontend` or `backend`
pod has no ready endpoints — see `task k8s:status`.

### Backend Connection Issues

Check what's actually running and why:

```bash
task k8s:status
task k8s:logs -- backend
task k8s:logs -- postgres

kubectl -n monthly-budget describe pod -l app.kubernetes.io/name=backend
kubectl -n monthly-budget logs job/backend-migrate    # Alembic output
```

The Tilt dashboard at http://localhost:10350 shows the same logs per resource,
plus buttons to re-run migrations, open a backend shell, and run tests.

## API Documentation

Once the backend is running, visit any of these. FastAPI mounts them outside the
`/api` prefix, so the ingress carries an explicit rule routing each to the backend:

- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc
- **OpenAPI schema**: http://localhost:8080/openapi.json
- **Prometheus metrics**: http://localhost:8080/metrics

They also work on the backend port-forward (http://localhost:8000/docs) if you
need to bypass the ingress.

## License

MIT
