# Data Layer Migration — Status

Companion to [data-layer-ports-design.md](./data-layer-ports-design.md), which holds the
design and the scope decisions. This file tracks what is done and what is left.

**Branch:** `feat/migrate-to-supabase` · Steps 0–6 are committed through `a541a25`, and
Steps 7 and 7.5 in the single commit on top of it. The working tree is clean apart from
`skills.lock.json`, which predates this work and is **not** part of it.

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
| Step 7: Receipt | `ReceiptRepository` on both adapters; `receipt_service` + receipts router off `get_db`; `category_suggestion` onto the Category port | — |
| Step 7.5: RefreshToken | `RefreshTokenRepository` on both adapters; `upsert_user` onto `uow.users`; all three `auth.py` endpoints off `get_db` | 794 |

Each row's suite count through Step 6 was verified by a full foreground run against PG17.
Steps 7 and 7.5 were verified together by one run — `794 passed in 472.93s`, no failures —
since 7 was never committed on its own.

Verified per file after all changes: `test_sqlalchemy_adapter.py` 91, `test_auth.py` 9,
`test_auth_integration.py` 2, `tests/unit` 232.
Ruff clean. `uv run mypy app` holds at **32** errors from the 37 baseline, none of them
in the ports or adapters.

Unit tier is now 232 tests, DB-free.

## Remaining work

- **Step 8** — the only router still holding a session is `app/routers/dev_auth.py`, and it
  keeps it permanently. What is left of this step is therefore documentation, not code:
  say *in `dev_auth.py`* why nobody should "finish the job" later, and confirm nothing else
  imports `get_db` outside that module and `app/deps/provider.py`.
  The router commits Step 8 was going to delete are already gone: the two in
  `app/routers/receipts.py` and the one in `delete_receipt` went with Step 7, because the
  router had to stop taking `db` at all.
- **mypy/ruff in CI — an open decision.** The design doc claimed the static conformance
  assertions in `app/adapters/conformance.py` were "checked by the existing mypy config."
  That is false: there is no `[tool.mypy]`, no `mypy.ini`, no `setup.cfg`, and
  `.github/workflows/ci.yml` runs only `uv run pytest`. Mitigated by
  `tests/unit/test_conformance.py`, which checks conformance at runtime and *is* in CI.
  `uv run mypy app` now has **32 errors across 12 files** (down from 37 — Step 7's rewrites
  removed several), still mostly `name-defined` in `app/models/*.py`. So adding mypy means
  fixing those or starting with a narrow include list. `app/ports/` and `app/adapters/` are
  clean today, and they are exactly the surface the conformance assertions exist to protect,
  which makes them the obvious first include. Ruff is already clean and would be nearly free.

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
- **Risk (g) was half wrong, and the half that was wrong cost a full suite run.** The design
  said `owns_transaction=False` would retire the bespoke NullPool engine in
  `tests/test_receipts_api.py`. It retires the *reason the module abandoned transaction
  isolation* — `receipt_service`'s real commits are now flushes and per-test rollback works
  there for the first time. It does **not** retire the engine, because that engine was quietly
  solving a second, unrelated problem: pytest-asyncio gives every test a fresh event loop, and
  `conftest.py`'s shared `_test_engine` uses a default QueuePool that hands loop-bound
  connections across test boundaries. Deleting the fixture produced **11
  `RuntimeError: Event loop is closed` failures**. It is restored, with that reason recorded in
  its own docstring so the next person does not re-derive it.
- **The three durability tests kept their assertions verbatim.** They opt out via a
  `_use_real_commits()` helper that pops the module's `get_uow` override, which restores the
  production `get_uow` and therefore `owns_transaction=True` over their `production_like_get_db`
  session. Nothing was weakened or deleted to reach green.
- **`test_categories_api.py` still has never been touched.** The invariant holds through Step 7.
  `test_receipts_api.py` did change, but only in its fixtures — the bespoke engine was in scope
  for this step by design, and no test body's assertions moved.
- **A caller can hide from a `module.function(` grep.** `tests/test_category_suggestion.py`
  imports `suggest_for_store` directly, so it survived the Step 7 survey and only surfaced in
  the full run, as 13 failures. When changing a service's signature, grep for the bare function
  name too.
- **`expense_service.delete_expense` lost its raw `db` parameter.** It only ever had one because
  Receipt had no repository; its docstring said "design doc Step 7" in as many words.
- **`test_auth.py` and `test_auth_integration.py` needed zero changes in Step 7.5**, the same
  invariant `test_categories_api.py` proved in the pilot. Both override `get_db`, and `get_uow`
  derives from it, so all three rewritten endpoints kept their tests verbatim.
- **`is_blacklisted` deliberately ignores `expires_at`.** The inline query it replaced selected
  on `jti` alone, and that is the correct contract, not an oversight to tidy up: the endpoint
  has already decoded the token, so an expired refresh token was rejected by
  `jwt.ExpiredSignatureError` several lines earlier. Filtering on expiry here would only open a
  window in which a revoked-but-expired jti reads as usable. Pinned by a test in both tiers.
- **`RefreshTokenRepository` is a port with no service behind it.** Two methods, both called
  straight from `app/routers/auth.py`. It exists to get the last non-`dev_auth` router off
  `AsyncSession`, not because the blacklist is an aggregate anyone models. Resist adding `get`
  or an expiry sweep to "round it out" — nothing prunes that table today.
- **`upsert_user` got its first direct tests** (`tests/unit/test_user_service.py`). Before the
  port it was reachable only through two `/api/auth/callback` cases that need Postgres, a mocked
  Google, and a patched JWT secret to assert one boolean; the avatar-clearing and
  `last_login_at` branches were never asserted at all.

## Operational notes

Steps 7 and 7.5 landed as one commit, not two. Step 7 was implemented but never
verified on its own, and every file the two steps share — `ports/unit_of_work.py`,
`adapters/conformance.py`, both UoW adapters, `tests/unit/{conftest,test_conformance}.py`,
`tests/test_sqlalchemy_adapter.py` — is modified by both, so splitting them would have meant
hunk-level surgery producing a first commit that could not pass its own tests. The single
794-test run covers both.

Do not start a manual `kubectl port-forward` alongside: do not start a manual `kubectl port-forward` alongside
`pg_port_forward.sh`. The script reuses whatever already listens on 5432 and says so, but two
forwards racing for the bind leaves one dead and can point a run at a different database — a
symptom that shows up as a spurious unique-violation failure, not as a connection error.
