"""fix frozen now() timestamp defaults

Revision ID: a71d4c9e2f60
Revises: e8b1c9f7a321
Create Date: 2026-07-26 23:45:00.000000

The original table migrations passed ``server_default="now()"`` — a plain Python
string, which SQLAlchemy emits as the SQL *literal* ``DEFAULT 'now()'``. Postgres
coerces that string to ``timestamptz`` once, at DDL time, and freezes the result:

    created_at | '2026-07-24 03:29:57.876095+00'::timestamp with time zone

Every row inserted without an explicit timestamp therefore received the moment
the migration ran, not the moment of insert. This migration replaces the frozen
literals with a real function call (``DEFAULT now()``) on all six affected
columns.

Existing rows are left untouched: their stored values are indistinguishable from
legitimately-inserted data, so backfilling would be guesswork.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a71d4c9e2f60"
down_revision: Union[str, None] = "e8b1c9f7a321"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column) pairs that were created with the frozen-literal default.
_TIMESTAMP_COLUMNS: tuple[tuple[str, str], ...] = (
    ("categories", "created_at"),
    ("expenses", "created_at"),
    ("expenses", "updated_at"),
    ("monthly_goals", "created_at"),
    ("monthly_goals", "updated_at"),
    ("receipts", "created_at"),
)


def upgrade() -> None:
    for table, column in _TIMESTAMP_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.dialects.postgresql.TIMESTAMP(timezone=True),
            existing_nullable=False,
            server_default=sa.func.now(),
        )


def downgrade() -> None:
    # Restore the original (broken) literal default so the schema round-trips.
    # The frozen instant it captures is the moment this downgrade runs rather
    # than the moment the original migration ran — the exact value cannot be
    # reconstructed, and only the literal-vs-function semantics matter here.
    for table, column in _TIMESTAMP_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.dialects.postgresql.TIMESTAMP(timezone=True),
            existing_nullable=False,
            server_default=sa.text("'now()'"),
        )
