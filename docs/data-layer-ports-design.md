# Data Layer: Port/Adapter Design

Design for moving the backend off direct `AsyncSession` use and behind a repository
seam, so the data layer can be backed by Postgres (local and hosted Supabase) or by
an in-memory fake, without application code knowing which.

## Scope decisions

These are settled; don't relitigate them:

- **Production uses hosted Supabase, reached through the existing async SQLAlchemy 2.0
  + asyncpg + Alembic stack.** Supabase is just Postgres. No `supabase-py`, no PostgREST.
- **Postgres only.** Supabase Auth and Supabase Storage are out of scope. Google OAuth,
  the custom JWT, and local-filesystem receipt storage all stay as they are.
- **Local dev runs stock `postgres:17-alpine`,** not `supabase/postgres`. See
  "Local dev image" below.
- **The in-memory adapter backs pure unit tests only.** The `*_integration.py` and
  `*_api.py` suites keep running against real Postgres. If a method needs pg_trgm,
  SQL aggregation, or cascade semantics, it is Postgres-tier and gets no fake.

## 1. Shape of the seam

**Per-aggregate repository `Protocol`s, aggregated behind a single injected `UnitOfWork`.**

Rejected:

- **One wide `DataStore` protocol** — ~55 methods. Every fake implements all or none, and
  there's no place to hang the "Postgres-only" boundary; one pg_trgm method makes the
  whole protocol un-fakeable.
- **Session-as-port** (typing `get_db`'s yield as a Protocol) — cheapest diff, but the
  protocol surface becomes `execute(select(...))`, so the fake must interpret SQLAlchemy
  Core expressions. That's a disguise, not a seam.
- **Use-case classes + domain entities** — right for greenfield, but here it means 9 entity
  classes and 9 mappers before any behaviour changes, plus rewiring every Pydantic
  `from_attributes` schema. Out of proportion.
- **Repos without a UoW** — `expense_service` touches Category + Expense + MonthlyGoal +
  Family; `receipt_service` touches Receipt + Expense + Category; `family_service` touches
  Family + FamilyMember + Invite + User. Four repo params per function is noise, and
  nothing would own `flush`/`commit`.

**`typing.Protocol`, not ABC.** Structural typing keeps `app/adapters/memory/` from importing
port implementations, mypy verifies conformance at the injection site, and services can
narrow to just what they need. The lost `NotImplementedError` safety net is bought back
statically via `app/adapters/conformance.py` holding assignments like
`_sql: CategoryRepository = SqlAlchemyCategoryRepository(cast(Any, None))`, checked by the
existing mypy config.

Do **not** use `@runtime_checkable` — it only checks method names, which is worse than nothing.

```python
# app/ports/errors.py
class PortError(Exception): ...

class UniqueViolation(PortError):
    def __init__(self, constraint: str):
        self.constraint = constraint

class ForeignKeyViolation(PortError): ...
class StaleObject(PortError): ...   # object used after rollback
```

Translating `sqlalchemy.exc.IntegrityError` into `UniqueViolation` inside the adapter is the
highest-value single change in this design: it's what lets the in-memory fake exercise the
409 paths in `category_service.create_category` and `monthly_goal_service.create_goal`, and
it removes `from sqlalchemy.exc import IntegrityError` from three services.

```python
# app/ports/repositories/category.py
class CategoryRepository(Protocol):
    async def get_in_family(self, category_id: UUID, family_id: UUID) -> Category | None: ...
    async def list_active(self, family_id: UUID) -> list[Category]: ...
    async def list_names(self, family_id: UUID) -> set[str]: ...
    async def first_active(self, family_id: UUID) -> Category | None: ...
    def add(self, category: Category) -> None: ...
    def add_all(self, categories: Sequence[Category]) -> None: ...
    async def delete(self, category: Category) -> None: ...

    # --- Postgres-tier only, no in-memory implementation ---
    async def find_similar_active(
        self, family_id: UUID, term: str, threshold: float
    ) -> Category | None: ...
    async def most_used_since(self, family_id: UUID, cutoff: date) -> Category | None: ...
```

## 2. Transaction boundaries

The current model is **not** "one commit at the end". Verified exceptions:

- `receipt_service._mark_failed` and `claim_receipt_for_retry` call `await db.commit()`
  mid-request, deliberately, so the audit row / retry claim survives the `HTTPException`
  that follows.
- `receipt_service` uses `db.begin_nested()` savepoints in three places.
- `category_service.create_category` / `update_category` and
  `monthly_goal_service.create_goal` / `copy_goals_from_previous_month` call
  `await db.rollback()` on `IntegrityError` — a *full* request rollback.
- `app/routers/receipts.py` calls `await db.commit()` in the router, and then `get_db`
  commits again.

So the UoW needs four operations, not two:

```python
# app/ports/unit_of_work.py
class UnitOfWork(Protocol):
    users: UserRepository
    families: FamilyRepository
    members: FamilyMemberRepository
    invites: InviteRepository
    categories: CategoryRepository
    expenses: ExpenseRepository
    goals: MonthlyGoalRepository
    receipts: ReceiptRepository
    tokens: RefreshTokenRepository
    budget: BudgetQuery                       # read model, see section 3

    async def flush(self) -> None: ...        # push writes, assign PKs, raise UniqueViolation
    async def commit(self) -> None: ...       # make durable (receipt paths only)
    async def rollback(self) -> None: ...
    def savepoint(self) -> AsyncContextManager[Savepoint]: ...
```

Rules:

- **Routers never commit.** Remove the two `await db.commit()` calls in
  `app/routers/receipts.py` and the one in `delete_receipt`. `get_uow`'s teardown owns it,
  exactly as `get_db` does today.
- **Services call `flush`, `savepoint`, and — only in `receipt_service` — `commit`.**

```python
# app/adapters/sqlalchemy/unit_of_work.py
class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession, *, owns_transaction: bool = True): ...

    async def flush(self) -> None:
        try:
            await self._s.flush()
        except IntegrityError as exc:
            raise _translate(exc) from exc

    async def commit(self) -> None:
        if self._owns:
            await self._s.commit()
        else:
            await self.flush()      # test tier: keep the outer transaction open
```

`owns_transaction=False` is what preserves conftest's isolation trick. Production wiring:

```python
# app/deps/provider.py
async def get_uow(session: AsyncSession = Depends(get_db)) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(session, owns_transaction=True)
```

Because FastAPI caches `Depends(get_db)` per request, every existing
`app.dependency_overrides[get_db] = override_get_db(db_session)` in `test_family_api.py`,
`test_expenses_api.py`, `test_receipts_api.py` and friends **keeps working untouched** — the
UoW is built over the test's already-`begin()`-ed session. Provide a test-only `get_uow`
override that flips `owns_transaction=False`, so `receipt_service`'s real commits become
flushes.

Caveat: the assertions in `test_receipts_api.py` that check durability *across* a rollback
need an `owns_transaction=True` fixture, or rewriting.

### In-memory fake transaction semantics

- Store is `dict[type, dict[UUID, object]]` holding **live ORM instances**, not copies, so
  in-place mutation works (see risk (b)).
- `flush()` — apply per-repo defaults (`id=uuid4()`, `created_at=now()`, both needed because
  Postgres supplies them via `server_default`), then check declared uniqueness index sets and
  raise `UniqueViolation`.
- `savepoint()` — push `copy.deepcopy(store)` onto a stack; on exception or explicit rollback,
  restore and pop; on clean exit, discard.
- `commit()` — `self._committed = deepcopy(store)`; clear the savepoint stack.
- `rollback()` — restore `store = deepcopy(self._committed)`, clear the stack, and mark every
  instance handed out since the last commit as **stale**, so attribute reads raise
  `StaleObject`. This is deliberately stricter than SQLAlchemy, and mirrors the real failure
  documented in `claim_receipt_for_retry` ("after a savepoint rollback the ORM instance's
  attributes are expired… raising MissingGreenlet").
- The fake does **not** implement `ON DELETE CASCADE` or CHECK constraints. Anything relying
  on them is Postgres-tier.

## 3. Port inventory

Derived from actual call sites. **PG** = Postgres-tier only, integration tests, no fake.

**UserRepository** — `get(id)` (dependencies.py:68, auth.py:118), `get_by_google_id`
(user_service:26), `get_by_email` (family_service:96, dev_auth:91), `add`.

**FamilyRepository** — `get(id)` (family_service ×3, expense_service:382, expenses.py grace
checks ×2), `get_with_members(id)` (family_service:69, eager `members→user`), `add`.

**FamilyMemberRepository** — `get_for_user_in_family(family_id, user_id)` (dependencies.py:87
and :115, family_service ×3, users.py:34), `get_any_for_user(user_id)` (family_service:33,
:103, :175), `get_with_family(user_id)` (users.py:36, `db.refresh(…, ["family"])`),
`get_with_user(family_id, user_id)` (family.py:163, `db.refresh(member, ["user"])`),
`count_admins(family_id)` (family_service:226, :281), `add`, `delete`.

**InviteRepository** — `get_pending(invite_id, user_id)`, `get_pending_for(family_id, user_id)`,
`list_pending_for_user_detailed(user_id)` (family.py:96, joinedload family + inviting_user),
`add`.

**CategoryRepository** — as sketched in section 1. `find_similar_active` is **PG** (pg_trgm
`func.similarity`, category_suggestion:20). `most_used_since` is **PG** (JOIN + GROUP BY +
`count() DESC LIMIT 1`, category_suggestion:68 — a ranking query whose tie-breaks a fake would
silently get wrong).

**ExpenseRepository** — `get_in_family(id, family_id)` *and*
`get_in_family_with_details(...)` (selectinload category/user/receipt — see risk (a)),
`list_for_month(family_id, year_month, category_id, limit, offset)`, `count_for_month(...)`,
`count_by_category(category_id)`, `add`, `delete`.

**MonthlyGoalRepository** — `list_for_month(family_id, year_month)`,
`get_in_family(goal_id, family_id)`, `latest_month_before(family_id, year_month)`
(string-comparison `MAX`, fake-able), `add`, `add_all`, `delete`.

**ReceiptRepository** — `get_in_family(id, family_id)`, `list_filtered(...)` (currently inline
at `app/routers/receipts.py:119` — move it here), `get_status(id)`, `add`, `delete`, and
`claim_for_retry(id) -> bool` **PG** (conditional `UPDATE … WHERE status='failed'`; the
guarantee *is* row-lock serialization, which a single-threaded fake trivially "passes" and
therefore proves nothing).

**RefreshTokenRepository** — `is_blacklisted(jti)`, `add`.

**BudgetQuery** (read model, not a repository) —
`category_spend_and_goals(family_id, year_month) -> list[CategorySpendRow]` **PG**.
`expense_service.get_budget_summary` is a 5-way aggregate with a subquery. Split it: the port
returns a plain DTO list, and the percentage/status/total math becomes a pure
`build_budget_summary(rows, is_editable)` function, unit-tested with literal data. This is the
one place a CQRS-style read model earns its keep.

**Not ported:** `app/routers/dev_auth.py` (`text("DELETE FROM expenses")`, `/api/test/reset`).
Dev-only, deliberately raw, stays on `get_db` permanently. Document it.

## 4. File layout

```
app/
  ports/
    __init__.py
    errors.py            # UniqueViolation, ForeignKeyViolation, StaleObject
    unit_of_work.py      # UnitOfWork, Savepoint protocols
    read_models.py       # CategorySpendRow, BudgetQuery protocol
    repositories/
      user.py  family.py  family_member.py  invite.py
      category.py  expense.py  monthly_goal.py  receipt.py  refresh_token.py
  adapters/
    conformance.py       # static mypy assertions for both adapters
    sqlalchemy/
      unit_of_work.py  errors.py  budget_query.py
      user_repo.py … receipt_repo.py
    memory/
      store.py           # snapshot/deepcopy engine, unique indexes, defaults
      unit_of_work.py
      user_repo.py … receipt_repo.py
  deps/
    provider.py          # get_uow, get_current_user, require_family_member/admin
tests/
  unit/                  # NEW: in-memory only, no DB, no event loop tricks
  (existing *_service / *_integration / *_api unchanged in shape)
```

## 5. Migration sequence

Each step lands independently with a green suite.

**Step 0 — scaffolding, zero behaviour change.** `app/ports/` + `SqlAlchemyUnitOfWork` +
`get_uow` layered over `get_db`. Nothing consumes it yet.

**Step 1 — pilot: Category.** Smallest surface (5 functions in
`app/services/category_service.py`), one cross-aggregate read (`count_by_category`), a real
unique-constraint 409 that proves the error-translation design, a pg_trgm method that proves
the PG-tier escape hatch, and it already has all three test tiers.
`test_categories_api.py` needs **no changes** — the `get_db` override propagates.
`test_categories_service.py` changes mechanically:
`category_service.create_category(db_session, …)` becomes
`SqlAlchemyUnitOfWork(db_session, owns_transaction=False)`.

**Step 2 — memory adapter for Category** plus the first `tests/unit/` tests. Purely additive.

**Step 3 — `app/dependencies.py`.** Move `get_current_user` / `require_family_member` /
`require_family_admin` onto `uow.users` / `uow.members`. Small, and it unblocks every remaining
router. Keep the module path (`app.dependencies`) so no router imports churn.

**Step 4 — MonthlyGoal.** Densest business logic (rollover, optimistic version, bulk upsert
diffing), so the best return on the fake. `bulk_upsert_goals` becomes almost entirely
fake-testable.

**Step 5 — Expense.** Extract `BudgetQuery` and the pure `build_budget_summary` **first**, as
its own commit.

**Step 6 — Family + FamilyMember + Invite + User, as one unit.** They're a single cluster in
`family_service.py`; splitting them leaves the service half-ported.

**Step 7 — Receipt, last.** Highest risk: mid-request commits, savepoints, retry claim.
Also retires `category_suggestion`'s duplicate queries onto the Category port, and
`expense_service.delete_expense`'s raw `db` parameter, which existed only because Receipt had
no repository.

**Step 7.5 — `RefreshTokenRepository`.** Not in the original sequence; Step 7 showed Step 8
cannot land without it. The inventory above lists the port (`is_blacklisted`, `add`) but no step
ever built it, and `app/routers/auth.py` needs it — three endpoints query
`RefreshTokenBlacklist` directly and call `user_service.upsert_user(db=db)`. Until that is
ported, "remove `get_db` from routers" is not a mechanical change.

**Step 8 — remove `get_db` from routers,** keeping it exported for `dev_auth`. After Step 7 the
only holdouts are `dev_auth.py` (permanent) and `auth.py` (blocked on Step 7.5). The router
`commit()` calls this step was meant to delete are already gone — they left with Step 7, since
the receipts router stopped taking `db` at all.

Coexistence works throughout: `get_uow` derives from `get_db`, and FastAPI caches it per
request, so a half-migrated router can take both and they share one session and one transaction.

## 6. Risks

**(a) Relationship traversal crosses the seam — in routers and schemas, not services.**
Verified:

- `ExpenseResponse` (`app/schemas/expense.py`) has `from_attributes=True` and reads
  `expense.category`, `expense.user` (via `validation_alias="user"`), and `receipt_status`,
  which is an ORM `@property` at `app/models/expense.py:93` reading `self.receipt`. Every
  expense response walks three relationships.
- `app/routers/family.py:_family_to_response` walks `family.members[*].user.email`.
- `app/routers/family.py:163` and `app/routers/users.py:36` call
  `await db.refresh(obj, ["user"|"family"])` **inside routers**.
- `expense_service.delete_expense:265` reads `expense.receipt.image_path`.

Consequence: eager-loading strategy becomes part of the port contract (`get_in_family` vs
`get_in_family_with_details`), and memory repos must explicitly populate `.category`, `.user`,
`.receipt`, `.members` on returned instances or `model_validate` raises `MissingGreenlet`.
This is a real, permanent cost of choosing repositories over entities. Accept it and name the
methods honestly.

**(b) The most dangerous spot: `app/routers/users.py:update_me`.** It mutates
`current_user.display_name` / `.timezone` and **never calls add, flush, or commit** — it
doesn't even take a `db` param. It relies entirely on the identity map of the session opened
by `get_current_user`, plus `get_db`'s teardown commit. Under any repository that returns a
detached object or a DTO, this becomes a **silent no-op that no current test would catch**.
Fix it explicitly in Step 3: take the uow, call `uow.users.add(user)` then `uow.flush()`.
The same implicit dirty-tracking pattern appears in every service
(`category.name = name; await db.flush()`), which is why the memory fake must hand back the
*same instance* it stores, never a copy.

**(c) ORM objects are the port's data type.** Opinionated call: **keep them**; don't introduce
domain entities in this migration. They're already thin declaratives and Pydantic is wired to
them; entities would double the diff and add 9 mappers. Cost: `app/ports/` transitively imports
SQLAlchemy (models import `app.database.Base`), so the ports are persistence-*indirect*, not
persistence-*ignorant*. The memory fake instantiates ORM classes unattached, which already
works — `tests/test_family_api.py:_make_member` does exactly that.

**(d) Server defaults.** `created_at` is `server_default=func.now()` on Category, Expense,
MonthlyGoal and Receipt; `id` defaults are Python-side. The memory store must apply both in
`flush()`, or `CategoryResponse.model_validate` fails on a required `created_at` in unit tests.

**(e) `expire_on_commit=False` is load-bearing.** `claim_receipt_for_retry:382` hand-syncs
`receipt.status` after commit because of it. Pin it in the adapter and comment why.

**(f) Service-level `rollback()` on IntegrityError** (category create/update, goal create,
copy_goals) discards the *whole request*, not just the failed insert. Port it literally to
preserve behaviour, but flag it: the correct fix is a savepoint, and that's a behaviour change
deserving its own PR and tests.

**(g) `tests/test_receipts_api.py`** carries a bespoke NullPool engine, and this entry used to
say it was solely because `receipt_service` really commits, so `owns_transaction=False` would
let it go away. **Step 7 disproved the "solely".** The engine had two jobs:

1. *Containing the real commits* — solved. `owns_transaction=False` turns them into flushes and
   the module has per-test rollback isolation for the first time.
2. *Event-loop isolation* — **not** solved, and nothing in this design touches it.
   pytest-asyncio gives each test a fresh event loop; `conftest.py`'s shared `_test_engine` has
   a default QueuePool that hands loop-bound connections to the next test. Removing the fixture
   produced 11 `RuntimeError: Event loop is closed` failures.

The engine stays, with the second reason documented on the fixture. The "audit row survives the
exception" assertions were preserved verbatim via a `_use_real_commits()` helper that pops the
module's `get_uow` override, restoring `owns_transaction=True` over a `production_like_get_db`
session.

Generalisation worth carrying forward: a test fixture that predates the seam may be load-bearing
for something the seam does not model. Delete one only after a run proves it redundant.

## Local dev image

`supabase/postgres` was evaluated and rejected. It is not a safe drop-in: its entrypoint runs
Supabase-specific migrations that reconfigure the `postgres` role and expect `supabase_admin`
to exist, and Supabase's own compose file mounts seven extra init SQL files, a custom
`postgresql.conf`, and a pgsodium key volume. Standalone in a plain StatefulSet it initializes
only partially. See [supabase/postgres#1219](https://github.com/supabase/postgres/issues/1219).

It would buy Supabase *platform* parity — roles, schemas and services that are out of scope
here. What this project needs is `pg_trgm` (ships in `postgresql-contrib`, already in stock
`postgres:*-alpine`) and JSONB, UUID and `TIMESTAMPTZ` (all core).

The parity gap that *does* matter is the version: hosted Supabase defaults new projects to
**PG17**, and the Supabase image line has no PG16 at all (it went 15 → 17 in June 2026). This
repo is on PG16, so dev, CI and prod are a major version apart. The fix is
`postgres:16-alpine` → `postgres:17-alpine` in `manifests/base/postgres/statefulset.yaml`,
with the CI service container bumped in lockstep.

PG17 cannot read a PG16 data directory: the dev PVC must be deleted and re-migrated.

## Connecting to hosted Supabase

Official guidance covers only `poolclass=NullPool` for the transaction pooler (:6543);
direct and session connections keep normal `pool_size`/`max_overflow`.

Community-corroborated but **not** in official docs — verify under load — for asyncpg against
Supavisor transaction mode, which rejects named prepared statements:

```python
connect_args={
    "statement_cache_size": 0,
    "prepared_statement_cache_size": 0,
    "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
}
```

with `pool_pre_ping=True` and a `pool_recycle`. This is reported to outperform plain
`NullPool` for long-lived services like this one.
[supabase/supabase#39227](https://github.com/supabase/supabase/issues/39227) is an open bug on
prepared-statement errors (transaction pooler) and burst-load timeouts (session pooler); treat
this area as evolving.

Alembic must use the session pooler (:5432) or the direct connection, since :6543 disallows
the prepared statements DDL needs. Hence a separate `DATABASE_MIGRATION_URL` setting that
falls back to `DATABASE_URL`.

The direct connection host is IPv6-only without the paid IPv4 add-on; the session pooler is
the IPv4-safe substitute. This matters for CI runners without IPv6 egress.
