# Manifests — AGENTS.md

kustomize manifests for the **local dev stack only** (k3d + Tilt). Production runs from pinned
GHCR images in a separate homelab repo (`manifests/apps/monthly-budget`); see
[docs/architecture.md](../docs/architecture.md).

## Layout

- **`base/`** — namespace, `postgres/` (StatefulSet `postgres:17-alpine` + Service + headless
  Service), `redis/`, `backend/` (Deployment + `job-migrate.yaml` Alembic Job + Service),
  `frontend/`, `ingress/`. The base has **no** ConfigMap/Secret; workloads `envFrom` the fixed
  names `app-config` / `app-secrets`, so always build an overlay.
- **`overlays/dev/`** — namespace `monthly-budget`, `configMapGenerator` from
  `config/app-config.env` and `secretGenerator` from `config/app-secrets.env`,
  `disableNameSuffixHash: true` (required: hashed names would roll pods and break Tilt
  live_update), `patches/fast-teardown.yaml`. Render: `kubectl kustomize manifests/overlays/dev`.
- **`../k3d.yaml`** — cluster `monthly-budget` (1 server + 1 agent), Traefik published on host
  :8080, registry `monthly-budget-registry` (host :5111 / in-cluster :5000).
- **`../Tiltfile`** — deploys the dev overlay, builds `monthly-budget-backend` /
  `monthly-budget-frontend`, live-syncs source. Hard-fails unless
  `k8s_context() == 'k3d-monthly-budget'` — start with `task up`, never bare `tilt up`.
  Resources: `postgres`, `redis`, `backend-migrate` (Job, recreated each apply), `backend`,
  `frontend`, and `cluster-config` (namespace, ConfigMap, Secret, ingress). UI buttons:
  `backend:migrate`, `backend:test`, `backend:shell`, `frontend:test`.
- There is no `docker compose`. Debug with `kubectl -n monthly-budget ...`,
  `task k8s:status`, `task k8s:logs -- <workload>`, or the Tilt UI (http://localhost:10350).

Changing the deploy topology or the env/config contract is a steering-doc trigger (root
`AGENTS.md` PR rule).

## Dev environment runbook

- Start: `task up` · pause: `task stop` (keeps data) · destroy: `task down`
- Exploratory browser (dev-login as `usera@e2e-test.com`): `task local:exploratory` or `task local:exploratory-seeded` (idempotent demo categories + current-month expenses). Requires `task e2e:install` once. Starts Tilt in the background if it is not already running; close the browser window to exit.
- Cluster `k3d-monthly-budget`, namespace `monthly-budget`, Tilt UI http://localhost:10350
- **App + API: http://localhost:8080** (Traefik ingress). `/api`, `/docs`, `/redoc`, `/openapi.json`, `/metrics` → backend:8000; `/` catch-all → frontend:5173. App and API share one origin, so the frontend's relative `/api/...` requests are same-origin. The frontend Deployment sets `VITE_HMR_CLIENT_PORT=8080`, so Vite advertises its HMR websocket on :8080 whichever URL you browse.
- Tilt also port-forwards `5173` (frontend pod) and `8000` (backend pod) for direct/single-service access — the Playwright config targets those.
- Postgres/Redis are not published to the host; in-cluster they are `postgres:5432` / `redis:6379`.
- Postgres data lives in a PVC inside the cluster. It survives `task stop`; `task down` and `task cluster:reset` destroy it.

### Config and secrets

In-cluster env comes from `manifests/overlays/dev/config/` — `app-config.env` → `ConfigMap/app-config`, `app-secrets.env` → `Secret/app-secrets`, both consumed wholesale via `envFrom`. Every value is a throwaway local-only placeholder, not a real credential. `ANTHROPIC_MOCK=true` is set there, which is why the e2e receipt specs are deterministic and no OpenRouter key is needed. `DECISION_MOCK=true` does the same for category auto-suggest (its `success` scenario picks the family's first active category).

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

**PG16 → PG17 (or any Postgres major-version bump):** Postgres cannot start a new major version against an old version's on-disk data directory — the `postgres` container will crash-loop on an existing PVC initialized by the prior major version. There is no in-place upgrade path for a throwaway dev volume; the fix is to delete the PVC and let migrations re-run from empty:

```bash
task db:reset
```
