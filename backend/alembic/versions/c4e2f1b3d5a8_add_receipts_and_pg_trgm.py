"""add receipts and pg_trgm

Revision ID: c4e2f1b3d5a8
Revises: c3f1d8a92e45
Create Date: 2026-04-19 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e2f1b3d5a8"
down_revision: Union[str, None] = "c3f1d8a92e45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable pg_trgm extension for fuzzy text matching
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2. Create receipts table
    op.create_table(
        "receipts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("uploaded_by", sa.UUID(), nullable=False),
        sa.Column("image_path", sa.Text(), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("parsed_date", sa.Date(), nullable=True),
        sa.Column("parsed_total_cents", sa.Integer(), nullable=True),
        sa.Column("parsed_merchant", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default="now()", nullable=False),
        sa.CheckConstraint("status IN ('processing','completed','failed')", name="ck_receipts_status"),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 3. Create receipts indexes
    op.create_index("idx_receipts_family", "receipts", ["family_id"], unique=False)
    op.create_index("idx_receipts_status", "receipts", ["status"], unique=False)

    # 4a. Null out any orphaned receipt_id values (can't satisfy FK otherwise)
    op.execute("UPDATE expenses SET receipt_id = NULL WHERE receipt_id IS NOT NULL")

    # 4b. Add FK constraint on expenses.receipt_id referencing receipts.id
    op.create_foreign_key(
        "fk_expenses_receipt",
        "expenses",
        "receipts",
        ["receipt_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 5. Add partial index on expenses(receipt_id) where not null
    op.create_index(
        "idx_expenses_receipt_id",
        "expenses",
        ["receipt_id"],
        unique=False,
        postgresql_where=sa.text("receipt_id IS NOT NULL"),
    )

    # 6. Add GIN index on categories.name using pg_trgm
    op.create_index(
        "idx_categories_name_trgm",
        "categories",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )


def downgrade() -> None:
    # Reverse in reverse order of upgrade

    # 6. Drop GIN trgm index on categories
    op.drop_index("idx_categories_name_trgm", table_name="categories")

    # 5. Drop partial index on expenses.receipt_id
    op.drop_index("idx_expenses_receipt_id", table_name="expenses")

    # 4. Drop FK constraint on expenses.receipt_id
    op.drop_constraint("fk_expenses_receipt", "expenses", type_="foreignkey")

    # 3. Drop receipts indexes
    op.drop_index("idx_receipts_status", table_name="receipts")
    op.drop_index("idx_receipts_family", table_name="receipts")

    # 2. Drop receipts table
    op.drop_table("receipts")

    # 1. Drop pg_trgm extension (only if no other objects depend on it)
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
