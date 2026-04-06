# Backend — CLAUDE.md

FastAPI + async SQLAlchemy 2.0 + asyncpg (PostgreSQL), structured logging via structlog.

## Commands

```bash
uv run pytest                          # Run all tests
uv run pytest tests/test_foo.py        # Single file
uv run pytest -k "test_name"           # Single test by name
uv run ruff check .                    # Lint
uv run ruff format .                   # Auto-format
uv run alembic upgrade head            # Apply migrations
uv run alembic revision --autogenerate -m "desc"  # Generate migration
```

IMPORTANT: Always use `uv run` to execute Python tools. Never use `pip` or bare `python`.

## Architecture

- **Entry point**: `app/main.py` — creates FastAPI app with lifespan handler, Prometheus instrumentation
- **Config**: `app/config.py` — pydantic-settings `Settings`, loads from env vars / `.env`
- **Database**: `app/database.py` — async engine, `AsyncSessionLocal`, `Base`, `get_db()` dependency
- **Layout**: `app/routers/` -> `app/services/` -> `app/models/` with `app/schemas/` for Pydantic I/O

Routers: auth, categories, dev_auth, expenses, family, health, monthly_goals, users
Models: User, Family, FamilyMember, Category, Expense, MonthlyGoal, Invite, RefreshTokenBlacklist

## Critical Patterns

**Everything is async.** All routes, database sessions, and tests use async/await. Never use sync SQLAlchemy APIs.

**Database sessions**: `get_db()` yields an `AsyncSession` that auto-commits on success and rolls back on exception. Use `Depends(get_db)` in routes.

**Alembic autogenerate**: Models MUST be imported in `app/database.py` (via `import app.models`) for autogenerate to detect them. If you add a new model file, ensure `app/models/__init__.py` imports it.

**Money is stored in cents** (`amount_cents: int`). Never use floats for money. Dates use `YYYY-MM` format for `year_month` fields.

## Testing

- **Framework**: pytest with `asyncio_mode = "auto"` — all async tests run automatically, no `@pytest.mark.asyncio` needed
- **Isolation**: Each test gets an `AsyncSession` wrapped in a transaction that rolls back at teardown (see `conftest.py:db_session`)
- **Auth**: Use the `authenticated_client` fixture — call it with a User to get an httpx `AsyncClient` with JWT cookies set
- **Factories**: `conftest.py` has plain async factory functions (not fixtures): `create_test_user()`, `create_test_family()`, `create_test_category()`, `create_test_expense()`, `create_test_monthly_goal()`, `create_test_invite()`. Call them with a `db_session`.
- **Google OAuth mock**: Use the `mock_google_oauth` fixture to patch `verify_oauth2_token`

## Hard Stops

- NEVER use sync database operations (`Session`, `create_engine` without async)
- NEVER use `pip` — this project uses `uv`
- NEVER commit `.env` files or hardcoded secrets
- NEVER use `float` for monetary amounts — use `int` cents
- NEVER add a model without importing it in `app/models/__init__.py`
