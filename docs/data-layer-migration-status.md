# Data Layer Migration — Status

Companion to [data-layer-ports-design.md](./data-layer-ports-design.md), which holds the
design and the scope decisions. This file tracks what is done and what is left.

**Branch:** `feat/migrate-to-supabase` · **Nothing is committed** — all work below is
uncommitted in the working tree.

## Scope, as decided

- Production uses **hosted Supabase reached as plain Postgres** through the existing async
  SQLAlchemy 2.0 + asyncpg + Alembic stack. No `supabase-py`, no PostgREST.
- **Postgres only.** Supabase Auth and Supabase Storage are out of scope. Google OAuth, the
  custom JWT, and local-filesystem receipt storage are unchanged.
- Local dev runs **stock `postgres:17-alpine`**, not `supabase/postgres` (see the design doc's
  "Local dev image" section for why).
- The in-memory adapter backs **unit tests only**. `*_integration.py` and `*_api.py` keep
  running against real Postgres.

## Done and verified

| Step | What landed | Suite |
|---|---|---|
| Supabase connection modes | `resolve_engine_kwargs` in `app/database.py` handles transaction pooler / session pooler / direct / local; Alembic on `DATABASE_MIGRATION_URL` | — |
| PG17 parity | `postgres:17-alpine` in the StatefulSet, both `wait-for-postgres` initContainers, and CI | 472 |
| Step 0–2: seam + Category pilot | `app/ports/`, `app/adapters/{sqlalchemy,memory}/`, `app/deps/provider.py` | 560 |
| Step 3: `dependencies.py` + `update_me` fix | User + FamilyMember repos; `get_current_user`, `require_family_member`, `require_family_admin` on ports | 598 |
| Steps 4–5: MonthlyGoal + Expense | `BudgetQuery` + pure `build_budget_summary`; both adapters | 717 |
| Step 6: Family cluster | `FamilyRepository` + `InviteRepository`; `family_service.py` fully off `get_db` | 736 |

Each row's suite count was verified by a full foreground run against PG17.

Unit tier is now 200 tests, DB-free, in ~0.26s.

## Remaining work

- **Step 7 — Receipt, the riskiest.** `receipt_service` commits mid-request on purpose in
  `_mark_failed` and `claim_receipt_for_retry` so audit rows survive the `HTTPException` that
  follows, and uses `begin_nested()` savepoints in three places.
  `claim_for_retry` is Postgres-tier: its guarantee *is* row-lock serialization, which a
  single-threaded fake would trivially "pass" and therefore prove nothing.
  Risk (e): `expire_on_commit=False` is load-bearing.
  Risk (g): `tests/test_receipts_api.py` carries a bespoke NullPool engine only because
  `receipt_service` really commits — `owns_transaction=False` should retire it, but the
  "audit row survives the exception" assertions must move to an `owns_transaction=True`
  fixture, not be weakened.
- **Step 8** — remove `get_db` from routers. Keep it exported for `app/routers/dev_auth.py`,
  which stays raw-SQL permanently for `/api/test/reset`. Also delete the two `await db.commit()`
  calls in `app/routers/receipts.py` and the one in `delete_receipt`.
- **mypy/ruff in CI — an open decision.** The design doc claimed the static conformance
  assertions in `app/adapters/conformance.py` were "checked by the existing mypy config."
  That is false: there is no `[tool.mypy]`, no `mypy.ini`, no `setup.cfg`, and
  `.github/workflows/ci.yml` runs only `uv run pytest`. Mitigated by
  `tests/unit/test_conformance.py`, which checks conformance at runtime and *is* in CI.
  `uv run mypy app` has **37 pre-existing errors** across 15 files (mostly `name-defined` in
  `app/models/*.py`), so adding mypy means fixing those or starting with a narrow include list.
  Ruff is already clean and would be nearly free to add.

## How to work on this

```bash
# Postgres tier (~7.5 min). Postgres is a k3d StatefulSet; this port-forwards it.
cd backend && ../scripts/dev/pg_port_forward.sh uv run pytest -q

# Unit tier — no database, no port-forward, sub-second
cd backend && uv run pytest tests/unit

cd backend && uv run ruff check . && uv run ruff format --check .
cd backend && uv run mypy app          # 37 pre-existing errors is the baseline
```

If Postgres won't start after a version change, `task db:reset` deletes the StatefulSet and
PVC and re-runs migrations. **PG17 cannot read a PG16 data directory** — that reset has
already been done once for the 16→17 bump.

## Notes worth keeping

- **`test_categories_api.py` needed zero changes** through the entire Category pilot. That is
  the proof the seam is transparent to callers: `dependency_overrides[get_db]` propagates
  through `get_uow` because FastAPI caches `Depends(get_db)` per request. If a future step
  forces an API test to change, the seam is wrong — stop and reconsider rather than editing
  the test.
- **The `update_me` bug was real**, and confirmed with a failing test before the fix. The
  endpoint returned 200 with the mutated fields while the repository never received the write.
  It worked only via the session identity map plus `get_db`'s teardown commit.
- **The memory store derives unique constraints and column defaults from the SQLAlchemy
  mapper** (`model_spec()`), with a hand-written shim only for `server_default`. An earlier cut
  hand-wrote a `MODEL_SPECS` table; that was removed because it would drift. Consequence: each
  new aggregate gets its fake constraints nearly free. Anonymous `Column(unique=True)`
  constraints are picked up automatically.
- **Memory snapshots clone column-by-column, not `copy.deepcopy`** — deepcopy walks
  SQLAlchemy's `InstanceState`, whose weakref back to the original is in `copy`'s atomic
  dispatch, so clones would carry state pointing at the wrong object.
- **`_translate(exc)` returns `None` for unclassifiable integrity errors** so the original
  `IntegrityError` propagates. The design doc's sketch would have relabelled NOT NULL and CHECK
  violations as port errors.
- **`User.created_at` and `FamilyMember.joined_at` have no default at all** — nullable and
  always app-supplied, unlike Category/Expense/MonthlyGoal which use `server_default=func.now()`.
- Services that call `rollback()` on `IntegrityError` discard the **whole request**, not just
  the failed insert. This was ported literally to stay behaviour-neutral. The correct fix is a
  savepoint, and it deserves its own PR (design doc risk (f)).
