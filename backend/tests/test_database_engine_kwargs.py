"""Unit tests for resolve_engine_kwargs.

Table-driven coverage of the three hosted-Supabase connection modes plus
plain local Postgres. Pure function, no live database required.
"""

import pytest

from app.database import resolve_engine_kwargs

LOCAL_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/monthly_budget"  # pragma: allowlist secret
DIRECT_URL = (
    "postgresql+asyncpg://postgres:pw@db.abcdefghijklmnop.supabase.co:5432/postgres"  # pragma: allowlist secret
)
SESSION_POOLER_URL = (
    "postgresql+asyncpg://postgres.abcdefghijklmnop:pw"
    "@aws-0-us-east-1.pooler.supabase.com:5432/postgres"  # pragma: allowlist secret
)
TRANSACTION_POOLER_URL = (
    "postgresql+asyncpg://postgres.abcdefghijklmnop:pw"
    "@aws-0-us-east-1.pooler.supabase.com:6543/postgres"  # pragma: allowlist secret
)

_POOLED_DEFAULTS = {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}


@pytest.mark.parametrize(
    "url",
    [
        pytest.param(LOCAL_URL, id="plain-local-postgres"),
        pytest.param(DIRECT_URL, id="direct-connection"),
        pytest.param(SESSION_POOLER_URL, id="supavisor-session-pooler"),
    ],
)
def test_resolve_engine_kwargs_uses_pooled_defaults(url: str) -> None:
    """Local, direct, and session-pooler connections keep today's pool behaviour."""
    assert resolve_engine_kwargs(url) == _POOLED_DEFAULTS


def test_resolve_engine_kwargs_transaction_pooler_disables_prepared_statements() -> None:
    """Supavisor's transaction pooler (6543) rejects named prepared statements."""
    kwargs = resolve_engine_kwargs(TRANSACTION_POOLER_URL)

    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == 300
    assert "pool_size" not in kwargs
    assert "max_overflow" not in kwargs

    connect_args = kwargs["connect_args"]
    assert connect_args["statement_cache_size"] == 0
    assert connect_args["prepared_statement_cache_size"] == 0

    name_func = connect_args["prepared_statement_name_func"]
    first, second = name_func(), name_func()
    assert first != second, "each call must yield a unique statement name"
    assert first.startswith("__asyncpg_")


def test_resolve_engine_kwargs_pooler_host_wrong_port_is_not_transaction_mode() -> None:
    """Only port 6543 on a pooler host triggers transaction-mode settings."""
    url = (
        "postgresql+asyncpg://postgres.abc:pw"
        "@aws-0-us-east-1.pooler.supabase.com:5433/postgres"  # pragma: allowlist secret
    )
    kwargs = resolve_engine_kwargs(url)
    assert kwargs == _POOLED_DEFAULTS
