# AGENTS.md

Monorepo for a family budgeting app: FastAPI backend, React frontend, kustomize manifests for a local k3d dev cluster. This file is the entry point; scoped `AGENTS.md` files hold the detail.

## Repo map

| Path | What lives there |
|---|---|
| `backend/` | FastAPI + async SQLAlchemy + Alembic. Hexagonal: routers → services → ports ← adapters |
| `frontend/` | React 19 + Vite + Chakra UI v3 + TanStack Query |
| `e2e/` | Playwright suite (needs the dev cluster; not in CI) |
| `manifests/` | kustomize `base/` + `overlays/dev/` for k3d; Tilt deploys them |
| `docs/` | `architecture.md`, generated `api-contract.md` / `openapi.json`, `adr/`, design notes, `specs/` |
| `scripts/` | dev helpers (`dev/pg_port_forward.sh`, `dev/ensure_dev_db.sh`, skills shim) |

## Where to read next

| Task touches… | Read |
|---|---|
| System shape, cross-component contracts, deploy | [docs/architecture.md](docs/architecture.md) |
| Any backend code | [backend/AGENTS.md](backend/AGENTS.md) |
| Routes, auth cookies, API schemas | [backend/app/routers/AGENTS.md](backend/app/routers/AGENTS.md), [docs/api-contract.md](docs/api-contract.md) |
| Repository/UnitOfWork interfaces | [backend/app/ports/AGENTS.md](backend/app/ports/AGENTS.md) |
| Business logic, LLM / decision-model calls | [backend/app/services/AGENTS.md](backend/app/services/AGENTS.md) |
| Tables and migrations | [backend/alembic/AGENTS.md](backend/alembic/AGENTS.md) |
| UI | [frontend/AGENTS.md](frontend/AGENTS.md), [DESIGN.md](DESIGN.md) |
| Dev cluster, Tilt, k3d, config/secrets | [manifests/AGENTS.md](manifests/AGENTS.md) |
| E2E tests | [e2e/CLAUDE.md](e2e/CLAUDE.md) |
| Why a past decision was made | [docs/adr/](docs/adr/) |

## Core commands (Taskfile)

```bash
task install        # deps + pre-commit hooks
task up             # k3d cluster + Tilt; app at http://localhost:8080 (stop: task stop, destroy: task down)
task lint           # pre-commit run --all-files (same hooks as CI)
task test           # backend (needs `task up`) + frontend tests
task be:test -- -k name    task fe:test    task fe:typecheck
task be:db:migrate  # in-cluster; be:db:revision MSG="..." runs on the host
task be:api-contract  # regenerate docs/api-contract.md + docs/openapi.json
```

## Global conventions

- Python: **uv** only (`uv run ...`, never pip); async everywhere; money is integer cents.
- The default branch is `master`; PRs target `master`. Squash-merge with a Conventional Commits title; the Release workflow derives the `backend/vX.Y.Z` / `frontend/vX.Y.Z` bump from it.
- Never commit secrets, `.env` files, or untracked agent dirs (`.agents/`, `.claude/` local state, `.codex/`, `.cursor/`, `.gemini/`).
- Tests mock every external call (OpenRouter chat + System One); `backend/test-scripts/` holds the opt-in live probes.
- Skills: see [.claude/rules/skills.md](.claude/rules/skills.md) and `task skills -- --help` (pass `--plain` when non-interactive).

## CI

`.github/workflows/ci.yml` on PRs to `master`: pre-commit (ruff, mypy, eslint, prettier, `tsc -b`, detect-secrets), backend pytest against Postgres 17 (includes the API-contract staleness check), frontend Vitest. `pr-lint.yaml` checks the title. On push to `master` touching `backend/` or `frontend/`, `semantic-release.yaml` (github-tag-action, per changed component) pushes a tag, and `build-push.yaml` publishes linux/amd64+arm64 images to `ghcr.io/jburns24/monthly-budget/{backend,frontend}`.

## PR rule

**Steering docs.** When you open or update a PR that makes a large architectural change — adding or removing a component or external provider, changing a port/repository interface, a DB table or migration strategy, an API schema shared with the frontend, an env/config contract, or the deploy topology — stop and ask the user whether any of the AGENTS.md steering docs (this file, `docs/architecture.md`, or the scoped `AGENTS.md` under the affected directory) should be updated in the same PR. Do not silently skip this question.
