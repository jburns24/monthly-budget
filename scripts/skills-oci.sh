#!/usr/bin/env bash
#
# Docker shim for the `skills-oci` CLI.
#
# Runs the ko-built skills-oci image against the repo root so the tool can
# read/write .agents/skills/, .claude/, skills.json and skills.lock.json in
# place. The image entrypoint IS the skills-oci binary, so arguments pass
# straight through: `scripts/skills-oci.sh <subcommand> [args...]`.
#
# Overrides (env vars):
#   SKILLS_OCI_IMAGE   Image ref to run (default: ghcr.io/jburns24/skills-oci:latest-main)
#   GITHUB_TOKEN       Forwarded to the container for registry auth. If unset,
#                      auto-derived from `gh auth token` (requires `gh auth login`
#                      once). Set it yourself to override, e.g. in CI.
#
set -euo pipefail

IMAGE="${SKILLS_OCI_IMAGE:-ghcr.io/jburns24/skills-oci:latest-main}"

# Operate on the repo root regardless of where the script is invoked from.
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Attach a TTY only when interactive, so the Bubble Tea TUI works locally but
# CI/non-interactive runs (which should pass --plain) don't hang.
TTY_FLAGS=()
if [ -t 0 ] && [ -t 1 ]; then
  TTY_FLAGS=(-it)
fi

# Registry auth: forward GITHUB_TOKEN for private pulls/push (public images
# still pull anonymously). We deliberately don't mount ~/.docker/config.json —
# on macOS/Docker Desktop it points credsStore at a host-only credential helper
# binary that doesn't exist inside the container, which breaks every pull
# (including public ones) with an "executable file not found" error.
if [ -z "${GITHUB_TOKEN:-}" ] && command -v gh >/dev/null 2>&1; then
  GITHUB_TOKEN="$(gh auth token 2>/dev/null || true)"
fi
AUTH_FLAGS=()
if [ -n "${GITHUB_TOKEN:-}" ]; then
  AUTH_FLAGS+=(-e "GITHUB_TOKEN=${GITHUB_TOKEN}")
fi

# Run as the host user so files written into the repo aren't owned by root.
# Note: ${arr[@]+"${arr[@]}"} guards empty-array expansion under `set -u`
# (macOS bash 3.2 treats an unset empty array as unbound otherwise).
exec docker run --rm ${TTY_FLAGS[@]+"${TTY_FLAGS[@]}"} \
  --user "$(id -u):$(id -g)" \
  -v "${ROOT}:/work" \
  -w /work \
  ${AUTH_FLAGS[@]+"${AUTH_FLAGS[@]}"} \
  "${IMAGE}" "$@"
