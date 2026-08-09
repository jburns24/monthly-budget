#!/usr/bin/env bash
# Launch a headed browser logged in as the e2e test user.
# Usage: ./scripts/dev/exploratory.sh [--seed]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SEED=0
for arg in "$@"; do
  case "$arg" in
    --seed) SEED=1 ;;
    -h|--help)
      echo "Usage: $0 [--seed]"
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $arg" >&2
      echo "Usage: $0 [--seed]" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$ROOT/e2e/node_modules/playwright" ]]; then
  echo "ERROR: e2e Playwright deps missing. Run: task e2e:install" >&2
  exit 1
fi

# Quick readiness check (tilt:ensure already waited; this catches races).
if ! curl -sf http://localhost:8080/api/health >/dev/null 2>&1; then
  echo "ERROR: http://localhost:8080/api/health is not healthy. Is Tilt up?" >&2
  exit 1
fi

echo "==> Ensuring Chromium is installed for Playwright"
(cd "$ROOT/e2e" && npx playwright install chromium)

echo "==> Opening exploratory browser (close the window to exit)"
cd "$ROOT/e2e"
if [[ "$SEED" -eq 1 ]]; then
  exec node scripts/exploratory.mjs --seed
else
  exec node scripts/exploratory.mjs
fi
