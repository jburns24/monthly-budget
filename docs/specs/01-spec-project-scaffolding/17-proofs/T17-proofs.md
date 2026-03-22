# T17 Proof Summary: Create GitHub Actions CI Workflow

**Task**: T04.2 - Create GitHub Actions CI workflow
**Status**: COMPLETED
**Timestamp**: 2026-03-22T00:00:00Z

## File Created

- `.github/workflows/ci.yml`

## Proof Artifacts

| # | File | Type | Status |
|---|------|------|--------|
| 1 | T17-01-actionlint.txt | cli (actionlint validation) | PASS |
| 2 | T17-02-file.txt | file (structure verification) | PASS |

## Summary

Created `.github/workflows/ci.yml` with three jobs:

1. **pre-commit** - Runs `pre-commit run --all-files` via the official `pre-commit/action@v3.0.1`,
   with caching for uv (keyed on `backend/uv.lock`) and npm (keyed on `frontend/package-lock.json`).
   Installs both backend and frontend dependencies before running so local hooks can access
   `uv run ruff`, `npx eslint`, `npx prettier`, and `npx tsc`.

2. **backend-tests** - Spins up a PostgreSQL 16-alpine service container with health checks,
   then runs `uv sync && uv run pytest` with `DATABASE_URL` pointing to the service container.

3. **frontend-tests** - Runs `npm ci && npm test -- --run` (vitest one-shot mode) on Node 20.

The workflow triggers on pull requests targeting the `main` branch.

## Validation

- `actionlint` (v1.7.11) reported no errors on the workflow file.
