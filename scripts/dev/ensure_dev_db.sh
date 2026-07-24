#!/usr/bin/env bash
# Ensure the dev Postgres volume matches Alembic migrations on the current branch.
# When alembic_version references a revision missing from backend/alembic/versions/,
# wipe mb_pg_data and wait for Postgres to come back (via Tilt or an existing container).
set -euo pipefail

CONTAINER="${DEV_DB_CONTAINER:-monthly-budget-db}"
VOLUME="${DEV_DB_VOLUME:-mb_pg_data}"
TILT_PORT="${TILT_PORT:-10350}"

POSTGRES_USER="${POSTGRES_USER:-monthly_budget}"
POSTGRES_DB="${POSTGRES_DB:-monthly_budget}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VERSIONS_DIR="${REPO_ROOT}/backend/alembic/versions"

tilt_is_running() {
  command -v tilt >/dev/null 2>&1 && lsof -ti ":${TILT_PORT}" >/dev/null 2>&1
}

container_running() {
  docker ps --format '{{.Names}}' | grep -qx "${CONTAINER}"
}

get_db_revision() {
  if ! container_running; then
    return 0
  fi

  docker exec "${CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
    "SELECT version_num FROM alembic_version LIMIT 1" 2>/dev/null | tr -d '[:space:]' || true
}

revision_exists_in_code() {
  local revision="$1"
  grep -rqE "revision[^=]*= *[\"']${revision}[\"']" "${VERSIONS_DIR}/"
}

wait_for_postgres() {
  local max_attempts="${1:-60}"

  for _ in $(seq 1 "${max_attempts}"); do
    if container_running && \
      docker exec "${CONTAINER}" pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "ERROR: Postgres did not become ready within ${max_attempts}s." >&2
  echo "Try: task db:reset (with Tilt running) or task up" >&2
  return 1
}

trigger_db_restart() {
  if tilt_is_running; then
    tilt trigger db --port "${TILT_PORT}" >/dev/null
  fi
}

reset_dev_db() {
  local reason="$1"

  echo "${reason}"
  echo "Removing dev database container and volume (${VOLUME}). Local dev data will be lost."

  docker rm -f "${CONTAINER}" 2>/dev/null || true
  docker volume rm "${VOLUME}" 2>/dev/null || true

  trigger_db_restart
  wait_for_postgres
}

if [[ "${1:-}" == "--force-reset" ]]; then
  reset_dev_db "Resetting dev database."
  exit 0
fi

current_revision="$(get_db_revision)"
if [[ -z "${current_revision}" ]]; then
  exit 0
fi

if revision_exists_in_code "${current_revision}"; then
  exit 0
fi

reset_dev_db "Stale migration revision '${current_revision}' is not in the current branch."
