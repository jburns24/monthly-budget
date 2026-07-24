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
#   GITHUB_TOKEN       Forwarded to the container for registry auth (optional)
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

# Forward Docker credentials read-only for private pulls / push. Public images
# pull anonymously, so this is best-effort. On macOS/Docker Desktop, creds are
# often in the keychain via a credential helper that isn't in the container —
# in that case prefer GITHUB_TOKEN, or run `push` from CI.
AUTH_FLAGS=()
if [ -f "${HOME}/.docker/config.json" ]; then
  AUTH_FLAGS+=(-v "${HOME}/.docker:/dockercfg:ro" -e "DOCKER_CONFIG=/dockercfg")
fi
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
