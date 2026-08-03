"""Adapters implementing the protocols in :mod:`app.ports`.

``sqlalchemy/`` is the real one, backed by Postgres (local or hosted Supabase).
``memory/`` backs pure unit tests only; anything needing pg_trgm, SQL
aggregation, or cascade semantics is Postgres tier and has no fake.

Application code must not import from this package — only
``app.deps.provider`` and the test suite construct adapters.
"""
