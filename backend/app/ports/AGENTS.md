# Ports — AGENTS.md

The persistence seam. Services depend on these `typing.Protocol`s; adapters in
`app/adapters/sqlalchemy/` (production) and `app/adapters/memory/` (unit tests only)
satisfy them structurally. Design history: [docs/data-layer-ports-design.md](../../../docs/data-layer-ports-design.md).

## What is here

| File | Contents |
|---|---|
| `unit_of_work.py` | `UnitOfWork`: one transaction plus every repository (`categories`, `expenses`, `users`, `families`, `members`, `invites`, `goals`, `receipts`, `recurring`, `tokens`, `budget`, `assets`, `asset_loans`, `asset_valuations`, `asset_contributions`, `hpi`) and four operations: `flush`, `commit`, `rollback`, `savepoint()` |
| `repositories/*.py` | One Protocol per aggregate; methods return ORM model instances |
| `read_models.py` | `BudgetQuery` — immutable DTO rows for the budget summary (no write path) |
| `errors.py` | Driver-independent `UniqueViolation` / `ForeignKeyViolation` (adapters translate DB errors into these) and `StaleObject` (raised only by the memory adapter) |

## Rules

- **Transaction boundary:** routers never commit; services call `flush()` and `savepoint()`. Only `receipt_service` calls `commit()` (it persists a failed-receipt audit row before raising).
- **Changing a Protocol** means changing *both* adapters and `app/adapters/conformance.py` (static assignments mypy checks in pre-commit/CI), and `tests/unit/test_conformance.py` re-checks at runtime. This is a steering-doc trigger — see the PR rule in the root `AGENTS.md`.
- **Postgres-tier methods** (pg_trgm similarity, GROUP BY rankings, the budget aggregate — e.g. `CategoryRepository.find_similar_active`, `most_used_since`) raise `NotImplementedError` in the memory adapter. Callers that run in unit tests must tolerate that (the category classifier does) or be tested against Postgres in `tests/test_sqlalchemy_adapter.py`.
- Do not add `@runtime_checkable`: it checks method names only.
- Raise `app.ports.errors` types from adapters, never `sqlalchemy.exc`, so services can map them to HTTP 409 without importing the driver.
- New aggregate: Protocol in `repositories/`, attribute on `UnitOfWork`, both adapters, conformance entry, memory-adapter tests in `tests/unit/`.
