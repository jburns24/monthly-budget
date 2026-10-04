"""add recurring_expenses and expenses.recurring_expense_id

Revision ID: d7a4b2c6e910
Revises: b2f8e1a4c907
Create Date: 2026-10-04 15:30:00.000000

A recurring rule is configured once and reconciled into ordinary ``expenses`` rows
on demand. ``uq_expenses_recurring_occurrence`` makes reconciliation idempotent: a
rule can never produce two rows for the same occurrence date.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7a4b2c6e910"
down_revision: Union[str, None] = "b2f8e1a4c907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recurring_expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("entry_type", sa.String(length=20), server_default="expense", nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("next_due_date", sa.Date(), nullable=False),
        sa.Column("occurrences_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name="ck_recurring_expenses_amount_positive"),
        sa.CheckConstraint(
            "frequency IN ('weekly', 'biweekly', 'monthly', 'yearly')",
            name="ck_recurring_expenses_frequency",
        ),
        sa.CheckConstraint("entry_type IN ('expense', 'income')", name="ck_recurring_expenses_entry_type"),
        sa.CheckConstraint(
            "(entry_type = 'expense' AND category_id IS NOT NULL) OR (entry_type = 'income' AND category_id IS NULL)",
            name="ck_recurring_expenses_entry_type_category",
        ),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_recurring_expenses_family", "recurring_expenses", ["family_id"])
    op.create_index(
        "idx_recurring_expenses_due",
        "recurring_expenses",
        ["family_id", "is_active", "next_due_date"],
    )

    op.add_column("expenses", sa.Column("recurring_expense_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_expenses_recurring_expense_id",
        "expenses",
        "recurring_expenses",
        ["recurring_expense_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "uq_expenses_recurring_occurrence",
        "expenses",
        ["recurring_expense_id", "expense_date"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_expenses_recurring_occurrence", table_name="expenses")
    op.drop_constraint("fk_expenses_recurring_expense_id", "expenses", type_="foreignkey")
    op.drop_column("expenses", "recurring_expense_id")
    op.drop_index("idx_recurring_expenses_due", table_name="recurring_expenses")
    op.drop_index("idx_recurring_expenses_family", table_name="recurring_expenses")
    op.drop_table("recurring_expenses")
