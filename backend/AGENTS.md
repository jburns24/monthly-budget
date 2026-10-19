# Backend — AGENTS.md

FastAPI + async SQLAlchemy 2.0 + asyncpg (PostgreSQL 17), Redis, Alembic, structlog. Python 3.12, managed with **uv**.

## Commands (from `backend/`)

```bash
uv sync                                                       # deps incl. dev group
../scripts/dev/pg_port_forward.sh uv run pytest               # all tests (or: task be:test -- -k name)
uv run pytest tests/unit                                      # in-memory adapter unit tests
uv run ruff check . && uv run ruff format .                   # lint + format (line length 120)
uv run python scripts/gen_api_contract.py                     # regenerate docs/api-contract.md + docs/openapi.json (task be:api-contract)
uv run python test-scripts/scan_receipt_probe.py              # LIVE OpenRouter receipt probe (see test-scripts/README.md)
```

Postgres is in the k3d cluster and unpublished; `pg_port_forward.sh` gives host commands `localhost:5432` (it silently reuses any existing listener — beware a local Postgres). Migrations: see [alembic/AGENTS.md](alembic/AGENTS.md).

## Layout (hexagonal)

| Path | Role | Scoped doc |
|---|---|---|
| `app/main.py` | App + lifespan (creates the shared `AsyncOpenAI` OpenRouter client on `app.state.llm`), CORS, request-id middleware, Prometheus `/metrics`, router registration (dev routers only in development/test) | — |
| `app/config.py` | pydantic-settings `Settings` (env / `.env`, unknown keys ignored); non-dev environments require a ≥32-char `JWT_SECRET` and `GOOGLE_CLIENT_ID` | — |
| `app/routers/` | HTTP layer: validation, `require_family_member`/role deps, rate-limit checks, status codes | [routers/AGENTS.md](app/routers/AGENTS.md) |
| `app/services/` | Business logic, LLM + decision-model calls, Redis rate limiter, pure asset math in `services/assets/` | [services/AGENTS.md](app/services/AGENTS.md) |
| `app/ports/` | `UnitOfWork` and repository `Protocol`s (the seam) | [ports/AGENTS.md](app/ports/AGENTS.md) |
| `app/adapters/sqlalchemy/`, `app/adapters/memory/` | Production adapters / in-memory adapters for unit tests | [ports/AGENTS.md](app/ports/AGENTS.md) |
| `app/deps/provider.py` | `get_uow` — a `SqlAlchemyUnitOfWork` over the request's `get_db` session | — |
| `app/models/`, `app/schemas/` | SQLAlchemy ORM models / Pydantic request-response models | — |
| `app/database.py` | Async engine, `AsyncSessionLocal`, `Base`, `get_db()` (commits on success, rolls back on exception) | — |
| `alembic/` | Async migrations | [alembic/AGENTS.md](alembic/AGENTS.md) |

## Critical patterns

- **Everything is async**; never use sync SQLAlchemy (`Session`, sync `create_engine`).
- **Routers never commit.** They take `uow: UnitOfWork = Depends(get_uow)`; `get_db`'s teardown owns the commit. `dev_auth.py` is the one deliberate raw-session exception.
- **Money is integer cents** (`amount_cents`); never `float`. `year_month` fields are `YYYY-MM`.
- **New model** → import it in `app/models/__init__.py` (which `app/database.py` imports) or autogenerate will not see it.
- **External calls are mocked in tests**: `LLM_MOCK` (receipt extraction) and `DECISION_MOCK` (category suggest; forced on by an autouse fixture in `tests/conftest.py`). Never hit OpenRouter from `tests/`.
- Logs are structured (`app.logging.get_logger`). Never log secrets or user free text (e.g. expense descriptions).

## Testing

- pytest with `asyncio_mode = "auto"` (no `@pytest.mark.asyncio`), `testpaths = ["tests"]`.
- `tests/*_api.py` / `*_integration.py` run against real Postgres; each test's `db_session` is a transaction rolled back at teardown. `tests/unit/` uses the in-memory adapters.
- Fixtures: `authenticated_client` (call with a `User` → httpx client with JWT cookies), `mock_google_oauth`. Factories in `conftest.py` are plain async functions: `create_test_user`, `create_test_family`, `create_test_category`, `create_test_expense`, `create_test_asset`, `create_test_monthly_goal`, `create_test_invite`, `create_test_receipt`.
- `tests/test_api_contract.py` fails when `docs/api-contract.md` / `docs/openapi.json` are stale.

## Hard stops

- NEVER use `pip` or bare `python` — `uv run`.
- NEVER commit `.env` files, API keys, or hardcoded secrets.
- NEVER use `float` for money.
- NEVER call `commit()` from a router.
