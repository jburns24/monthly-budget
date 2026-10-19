# Alembic — AGENTS.md

Async Alembic (`env.py` uses `async_engine_from_config`). Target metadata is `app.database.Base`,
which sees every model because `app/database.py` imports `app.models` — a model missing from
`app/models/__init__.py` is invisible to autogenerate.

## Where migrations run

| Environment | How |
|---|---|
| Dev (k3d) | `backend-migrate` Job on every Tilt apply; `task be:db:migrate` / `be:db:downgrade` run **in-cluster** via `kubectl exec deploy/backend` |
| New revision | `task be:db:revision MSG="..."` runs on the **host** through `scripts/dev/pg_port_forward.sh` (it writes a `.py`; a file written in the pod never reaches git). Migrate to head first |
| CI | `alembic upgrade head` before pytest, against Postgres 17 |
| Prod | the image's `entrypoint.sh` runs `alembic upgrade head` before gunicorn on every pod start (hence `Recreate`, one replica) |

`env.py` connects with `DATABASE_MIGRATION_URL` (falls back to `DATABASE_URL`). Hosted
Supabase's transaction pooler (:6543) rejects the prepared statements Alembic's DDL needs, so
point migrations at the session pooler or a direct connection.

## Rules

- One linear history (`down_revision` chain; check `alembic heads` shows one head). Rebase your
  revision onto the current head rather than merging heads.
- Every migration needs a working `downgrade()`. Migrations run on prod startup, so keep them
  fast and backward-compatible with the previous image where possible (add nullable → backfill →
  constrain in a later release).
- Extensions are created in migrations (`c4e2f1b3d5a8` adds `pg_trgm`, which category matching needs).
- Timestamp defaults: `server_default=sa.text("now()")` / `sa.func.now()`, never the plain string
  `"now()"` — that becomes a frozen literal (see `a71d4c9e2f60_fix_frozen_now_timestamp_defaults`).
- detect-secrets skips `versions/*.py`; some revision ids still carry `# pragma: allowlist secret`.
- `tests/test_migrations.py` round-trips upgrade/downgrade; extend it for risky migrations.
- Stale dev DB after a branch switch → `scripts/dev/ensure_dev_db.sh` (run by `be:db:migrate`)
  tells you to `task db:reset`.
- A new table or migration-strategy change is a steering-doc trigger (root `AGENTS.md` PR rule).
