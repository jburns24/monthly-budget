#!/usr/bin/env bash
# Detect a dev database left on a migration that no longer exists on this branch.
#
# Switch branches and the DB keeps whatever alembic_version the old branch put
# there. If that revision file is gone, `alembic upgrade head` dies with a bare
#   FAILED: Can't locate revision identified by '<hash>'
# which gives no hint that the fix is to wipe the volume. This script catches it
# first and says so.
#
# Exit codes:
#   0  DB is fine, absent, or empty — nothing to do
#   1  DB is on a revision this branch does not have
#
# WHAT CHANGED IN THE K8S MIGRATION
# This used to `docker exec monthly-budget-db psql`, `docker volume rm
# mb_pg_data` and `tilt trigger db` — none of which exist any more. Postgres is
# now a StatefulSet pod backed by a PVC and the Tilt resource is named
# `postgres`. It is also now DETECT-ONLY: the old `--force-reset` flag is gone
# because the root Taskfile's `task db:reset` already owns the destructive path
# (delete statefulset + pvc, then re-trigger postgres and backend-migrate), and
# duplicating that here would mean two places to keep correct. Refusing loudly
# also beats silently destroying a database as a side effect of `db:migrate`.
set -euo pipefail

NAMESPACE="${NAMESPACE:-monthly-budget}"
POSTGRES_USER="${POSTGRES_USER:-monthly_budget}"
POSTGRES_DB="${POSTGRES_DB:-monthly_budget}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VERSIONS_DIR="${REPO_ROOT}/backend/alembic/versions"

# A missing pod is not a failure: a fresh cluster has nothing to be stale about,
# and backend-migrate will build the schema from scratch.
pod="$(kubectl -n "${NAMESPACE}" get pod -l app.kubernetes.io/name=postgres \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"

if [[ -z "${pod}" ]]; then
  exit 0
fi

if ! kubectl -n "${NAMESPACE}" wait --for=condition=ready "pod/${pod}" --timeout=5s >/dev/null 2>&1; then
  echo "==> ${pod} is not ready; skipping the stale-migration check."
  exit 0
fi

# psql over the pod's local socket is trusted, so no password is needed here.
# Every row matters: alembic_version holds one per head, and any one of them
# going missing is enough to break `upgrade`.
revisions="$(kubectl -n "${NAMESPACE}" exec "${pod}" -c postgres -- \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
  'SELECT version_num FROM alembic_version' 2>/dev/null | tr -d '\r' || true)"

# Empty means a fresh database or no alembic_version table yet — both fine.
if [[ -z "$(echo "${revisions}" | tr -d '[:space:]')" ]]; then
  exit 0
fi

stale=()
while IFS= read -r revision; do
  revision="$(echo "${revision}" | tr -d '[:space:]')"
  [[ -z "${revision}" ]] && continue
  if ! grep -rqE "revision[^=]*= *[\"']${revision}[\"']" "${VERSIONS_DIR}/"; then
    stale+=("${revision}")
  fi
done <<<"${revisions}"

if [[ ${#stale[@]} -eq 0 ]]; then
  exit 0
fi

echo "ERROR: the dev database is on migration revision(s) that this branch does not have:" >&2
for revision in "${stale[@]}"; do
  echo "         ${revision}" >&2
done
echo "       This normally means you switched branches. Wipe the dev database" >&2
echo "       and let migrations re-apply from scratch (local dev data is lost):" >&2
echo "         task db:reset" >&2
exit 1
