"""Tests for Alembic database migrations.

Verifies that migrations apply and revert cleanly (round-trip).
"""

import os
import subprocess

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

# Use the venv's alembic binary directly — avoids import shadowing by the local alembic/ dir
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ALEMBIC_BIN = os.path.join(_BACKEND_DIR, ".venv", "bin", "alembic")


def _run_alembic(*args: str) -> None:
    result = subprocess.run(
        [_ALEMBIC_BIN, *args],
        capture_output=True,
        text=True,
        cwd=_BACKEND_DIR,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic {' '.join(args)} failed:\n{result.stderr}")


@pytest.mark.asyncio
async def test_c4e2f1b3d5a8_upgrade_downgrade() -> None:
    """Migration c4e2f1b3d5a8 upgrades and downgrades cleanly."""

    # Upgrade to head (includes c4e2f1b3d5a8)
    _run_alembic("upgrade", "head")

    # Verify receipts table exists with expected columns
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:

        def check_schema(sync_conn):  # type: ignore[no-untyped-def]
            inspector = inspect(sync_conn)
            tables = inspector.get_table_names()
            assert "receipts" in tables, "receipts table should exist after upgrade"

            columns = {c["name"] for c in inspector.get_columns("receipts")}
            expected_columns = {
                "id",
                "family_id",
                "uploaded_by",
                "image_path",
                "raw_response",
                "parsed_date",
                "parsed_total_cents",
                "parsed_merchant",
                "status",
                "error_message",
                "created_at",
            }
            assert expected_columns.issubset(columns), f"Missing columns: {expected_columns - columns}"

            indexes = {idx["name"] for idx in inspector.get_indexes("receipts")}
            assert "idx_receipts_family" in indexes
            assert "idx_receipts_status" in indexes

            fk_constraints = inspector.get_foreign_keys("expenses")
            fk_names = {fk.get("name") for fk in fk_constraints}
            assert "fk_expenses_receipt" in fk_names, "FK fk_expenses_receipt should exist"

            expense_indexes = {idx["name"] for idx in inspector.get_indexes("expenses")}
            assert "idx_expenses_receipt_id" in expense_indexes

            category_indexes = {idx["name"] for idx in inspector.get_indexes("categories")}
            assert "idx_categories_name_trgm" in category_indexes

        await conn.run_sync(check_schema)

        # Verify pg_trgm extension is present
        result = await conn.execute(text("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'"))
        row = result.fetchone()
        assert row is not None, "pg_trgm extension should be installed"

    await engine.dispose()

    # Downgrade one step back (removes c4e2f1b3d5a8)
    _run_alembic("downgrade", "-1")

    # Verify receipts table is gone and FK is removed
    engine2 = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine2.connect() as conn:

        def check_downgrade(sync_conn):  # type: ignore[no-untyped-def]
            inspector = inspect(sync_conn)
            tables = inspector.get_table_names()
            assert "receipts" not in tables, "receipts table should be gone after downgrade"

            fk_constraints = inspector.get_foreign_keys("expenses")
            fk_names = {fk.get("name") for fk in fk_constraints}
            assert "fk_expenses_receipt" not in fk_names, "FK fk_expenses_receipt should be removed"

            expense_indexes = {idx["name"] for idx in inspector.get_indexes("expenses")}
            assert "idx_expenses_receipt_id" not in expense_indexes

            category_indexes = {idx["name"] for idx in inspector.get_indexes("categories")}
            assert "idx_categories_name_trgm" not in category_indexes

        await conn.run_sync(check_downgrade)

    await engine2.dispose()

    # Re-apply upgrade to leave DB in clean state for other tests
    _run_alembic("upgrade", "head")
