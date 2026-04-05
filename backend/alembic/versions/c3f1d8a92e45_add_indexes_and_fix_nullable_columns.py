"""add indexes and fix nullable columns

Revision ID: c3f1d8a92e45
Revises: ab32c81d8481
Create Date: 2026-04-05 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f1d8a92e45"
down_revision: Union[str, None] = "ab32c81d8481"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing indexes on expenses
    op.create_index(
        "idx_expenses_family_category_month",
        "expenses",
        ["family_id", "category_id", "year_month"],
        unique=False,
    )
    op.create_index("idx_expenses_user", "expenses", ["user_id"], unique=False)
    op.create_index("idx_expenses_date", "expenses", ["expense_date"], unique=False)

    # Make expenses.expense_date NOT NULL
    op.alter_column("expenses", "expense_date", existing_type=sa.Date(), nullable=False)

    # Make expenses.year_month NOT NULL
    op.alter_column("expenses", "year_month", existing_type=sa.String(length=7), nullable=False)

    # Make monthly_goals.amount_cents NOT NULL
    op.alter_column("monthly_goals", "amount_cents", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    # Reverse nullable changes
    op.alter_column("monthly_goals", "amount_cents", existing_type=sa.Integer(), nullable=True)
    op.alter_column("expenses", "year_month", existing_type=sa.String(length=7), nullable=True)
    op.alter_column("expenses", "expense_date", existing_type=sa.Date(), nullable=True)

    # Drop added indexes
    op.drop_index("idx_expenses_date", table_name="expenses")
    op.drop_index("idx_expenses_user", table_name="expenses")
    op.drop_index("idx_expenses_family_category_month", table_name="expenses")
