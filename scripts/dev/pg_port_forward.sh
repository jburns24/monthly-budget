#!/usr/bin/env bash
# Run a command with the dev Postgres reachable on localhost:5432.
#
#   scripts/dev/pg_port_forward.sh uv run pytest
#   scripts/dev/pg_port_forward.sh uv run alembic revision --autogenerate -m "msg"
#
# WHY THIS EXISTS
# Postgres used to be a `docker run` container publishing 5432 on the host, so
# host-side tooling could just connect. It is now a StatefulSet in the k3d
# cluster, and the Tiltfile deliberately does not port-forward it. But anything
# that has to run on the host still expects localhost:5432, because
# backend/app/config.py resolves the repo-root .env regardless of CWD and that
# file pins DATABASE_URL to localhost:5432.
#
# Two things need the host, and only the host:
#   * pytest  -- the suite must run against the working tree, not the image.
#   * alembic revision --autogenerate -- it WRITES a .py file. Run in-cluster
#     and the new migration lands in the container's overlayfs, where Tilt will
#     never copy it back (live_update is host -> container only) and the next
#     rebuild silently discards it.
# `alembic upgrade`/`downgrade` touch no files, so those run in-cluster instead;
# see backend/Taskfile.yml.
#
# If something is already listening on the port (a Tilt port_forward, a stray
# container, a manual kubectl port-forward) this reuses it rather than fighting
# it for the bind.
set -euo pipefail

NAMESPACE="${NAMESPACE:-monthly-budget}"
LOCAL_PORT="${DEV_DB_PORT:-5432}"
READY_TIMEOUT="${DEV_DB_READY_TIMEOUT:-120s}"

if [[ $# -eq 0 ]]; then
  echo "usage: $(basename "$0") <command> [args...]" >&2
  exit 64
fi

# bash's /dev/tcp avoids depending on nc/lsof being present and behaving the
# same across macOS and Linux.
port_is_open() {
  (exec 3<>"/dev/tcp/127.0.0.1/${LOCAL_PORT}") 2>/dev/null
}

if port_is_open; then
  # Deliberately does NOT verify that the listener is the cluster's Postgres.
  # If you run a local Postgres.app / Homebrew postgres on 5432 it wins, and the
  # command below talks to that instead of the pod. Say so loudly rather than
  # silently testing against the wrong database; DEV_DB_PORT overrides the port.
  echo "==> NOTE: something already serves 127.0.0.1:${LOCAL_PORT}; using it as-is"
  echo "    rather than port-forwarding the cluster. If that is a local Postgres"
  echo "    install, stop it (or set DEV_DB_PORT) to target the pod instead."
  exec "$@"
fi

if ! kubectl -n "${NAMESPACE}" get statefulset/postgres >/dev/null 2>&1; then
  echo "ERROR: no statefulset/postgres in namespace '${NAMESPACE}', and nothing" >&2
  echo "       is listening on 127.0.0.1:${LOCAL_PORT}." >&2
  echo "       Start the dev environment first: task up" >&2
  exit 1
fi

# port-forward fails outright against a pod that is not accepting connections
# yet, so gate on readiness instead of retrying the forward.
echo "==> Waiting for Postgres to be ready in namespace '${NAMESPACE}'"
kubectl -n "${NAMESPACE}" wait --for=condition=ready pod \
  -l app.kubernetes.io/name=postgres --timeout="${READY_TIMEOUT}"

echo "==> Port-forwarding svc/postgres to 127.0.0.1:${LOCAL_PORT}"
kubectl -n "${NAMESPACE}" port-forward svc/postgres "${LOCAL_PORT}:5432" >/dev/null 2>&1 &
PF_PID=$!

# shellcheck disable=SC2329  # invoked indirectly by the trap below
cleanup() {
  # `kill` on an already-dead forward is not an error worth surfacing.
  kill "${PF_PID}" 2>/dev/null || true
  wait "${PF_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 40); do
  port_is_open && break
  # If the forward died (bad port, RBAC, pod vanished) stop waiting on it.
  if ! kill -0 "${PF_PID}" 2>/dev/null; then
    echo "ERROR: kubectl port-forward exited before the port opened." >&2
    echo "       Retry manually to see why:" >&2
    echo "       kubectl -n ${NAMESPACE} port-forward svc/postgres ${LOCAL_PORT}:5432" >&2
    exit 1
  fi
  sleep 0.25
done

if ! port_is_open; then
  echo "ERROR: 127.0.0.1:${LOCAL_PORT} never opened." >&2
  exit 1
fi

# Run the command without `set -e` aborting before the trap can report, and
# propagate its exit status so callers (task, CI) still see failures.
set +e
"$@"
status=$?
set -e
exit "${status}"
