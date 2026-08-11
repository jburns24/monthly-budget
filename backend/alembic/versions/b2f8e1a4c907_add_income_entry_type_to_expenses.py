"""add income entry_type to expenses

Revision ID: b2f8e1a4c907
Revises: a71d4c9e2f60
Create Date: 2026-08-11 02:50:00.000000

Phase 0 income-tracking contract: expenses gain ``entry_type`` and
``is_starting_balance``, ``category_id`` becomes nullable for income rows, and
DB CHECKs / a partial unique index enforce the invariants.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2f8e1a4c907"
down_revision: Union[str, None] = "a71d4c9e2f60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "expenses",
        sa.Column("entry_type", sa.String(length=20), server_default="expense", nullable=False),
    )
    op.add_column(
        "expenses",
        sa.Column("is_starting_balance", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.alter_column("expenses", "category_id", existing_type=sa.UUID(), nullable=True)

    op.create_check_constraint(
        "ck_expenses_entry_type",
        "expenses",
        "entry_type IN ('expense', 'income')",
    )
    op.create_check_constraint(
        "ck_expenses_entry_type_category",
        "expenses",
        "(entry_type = 'expense' AND category_id IS NOT NULL) OR (entry_type = 'income' AND category_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_expenses_starting_balance_income",
        "expenses",
        "(NOT is_starting_balance) OR (entry_type = 'income')",
    )
    op.create_index(
        "uq_expenses_starting_balance_per_family_month",
        "expenses",
        ["family_id", "year_month"],
        unique=True,
        postgresql_where=sa.text("is_starting_balance"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_expenses_starting_balance_per_family_month",
        table_name="expenses",
        postgresql_where=sa.text("is_starting_balance"),
    )
    op.drop_constraint("ck_expenses_starting_balance_income", "expenses", type_="check")
    op.drop_constraint("ck_expenses_entry_type_category", "expenses", type_="check")
    op.drop_constraint("ck_expenses_entry_type", "expenses", type_="check")

    # Income rows (null category_id) must be removed before restoring NOT NULL.
    op.execute("DELETE FROM expenses WHERE entry_type = 'income'")
    op.alter_column("expenses", "category_id", existing_type=sa.UUID(), nullable=False)

    op.drop_column("expenses", "is_starting_balance")
    op.drop_column("expenses", "entry_type")
