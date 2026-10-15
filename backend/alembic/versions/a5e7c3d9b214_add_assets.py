"""add assets, loans, valuations, contributions, house price index and expense asset links

Revision ID: a5e7c3d9b214
Revises: d7a4b2c6e910
Create Date: 2026-10-14 10:00:00.000000

Assets (house/vehicle/other) with at most one loan, manual valuations, historical
contributions, and a local cache of the FHFA house price index. Expenses and
recurring expenses gain a nullable ``asset_id`` (ON DELETE SET NULL) and
``asset_role``. The check on the pair is deliberately only "a role needs an asset":
SET NULL on ``asset_id`` alone must not violate it, so the service clears both
before deleting an asset.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a5e7c3d9b214"
down_revision: Union[str, None] = "d7a4b2c6e910"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLE_CHECK = "asset_role IS NULL OR asset_role IN ('loan_payment', 'improvement', 'maintenance', 'carrying_cost')"
_ROLE_REQUIRES_ASSET_CHECK = "asset_role IS NULL OR asset_id IS NOT NULL"


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("purchase_price_cents", sa.Integer(), nullable=False),
        sa.Column("down_payment_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("closing_costs_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("address_line1", sa.String(length=200), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=2), nullable=True),
        sa.Column("zip_code", sa.String(length=5), nullable=True),
        sa.Column("annual_depreciation_rate", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("sold_date", sa.Date(), nullable=True),
        sa.Column("sale_price_cents", sa.Integer(), nullable=True),
        sa.Column("selling_costs_cents", sa.Integer(), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("asset_type IN ('house', 'vehicle', 'other')", name="ck_assets_asset_type"),
        sa.CheckConstraint("purchase_price_cents >= 0", name="ck_assets_purchase_price_nonnegative"),
        sa.CheckConstraint("down_payment_cents >= 0", name="ck_assets_down_payment_nonnegative"),
        sa.CheckConstraint("closing_costs_cents >= 0", name="ck_assets_closing_costs_nonnegative"),
        sa.CheckConstraint(
            "(sold_date IS NULL AND sale_price_cents IS NULL AND selling_costs_cents IS NULL) "
            "OR (sold_date IS NOT NULL AND sale_price_cents IS NOT NULL)",
            name="ck_assets_sold_fields",
        ),
        sa.CheckConstraint(
            "sale_price_cents IS NULL OR sale_price_cents >= 0", name="ck_assets_sale_price_nonnegative"
        ),
        sa.CheckConstraint(
            "selling_costs_cents IS NULL OR selling_costs_cents >= 0", name="ck_assets_selling_costs_nonnegative"
        ),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_assets_family", "assets", ["family_id"])

    op.create_table(
        "asset_loans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_amount_cents", sa.Integer(), nullable=False),
        sa.Column("annual_interest_rate", sa.Numeric(precision=7, scale=5), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=False),
        sa.Column("first_payment_date", sa.Date(), nullable=False),
        sa.Column("monthly_payment_cents", sa.Integer(), nullable=True),
        sa.Column("escrow_monthly_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("original_amount_cents > 0", name="ck_asset_loans_original_amount_positive"),
        sa.CheckConstraint("term_months > 0", name="ck_asset_loans_term_positive"),
        sa.CheckConstraint(
            "monthly_payment_cents IS NULL OR monthly_payment_cents > 0", name="ck_asset_loans_payment_positive"
        ),
        sa.CheckConstraint("escrow_monthly_cents >= 0", name="ck_asset_loans_escrow_nonnegative"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", name="uq_asset_loans_asset"),
    )

    op.create_table(
        "asset_loan_balance_corrections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("loan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("balance_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("balance_cents >= 0", name="ck_asset_loan_corrections_balance_nonnegative"),
        sa.ForeignKeyConstraint(["loan_id"], ["asset_loans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("loan_id", "as_of_date", name="uq_asset_loan_corrections_loan_date"),
    )

    op.create_table(
        "asset_valuations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("value_cents", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("value_cents >= 0", name="ck_asset_valuations_value_nonnegative"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "as_of_date", name="uq_asset_valuations_asset_date"),
    )

    op.create_table(
        "asset_contributions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contribution_date", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name="ck_asset_contributions_amount_positive"),
        sa.CheckConstraint(
            "role IN ('improvement', 'maintenance', 'carrying_cost')", name="ck_asset_contributions_role"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_asset_contributions_asset", "asset_contributions", ["asset_id"])

    op.create_table(
        "house_price_index",
        sa.Column("series", sa.String(length=10), nullable=False),
        sa.Column("geo_code", sa.String(length=3), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.Integer(), nullable=False),
        sa.Column("index_value", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.CheckConstraint("series IN ('zip3', 'state')", name="ck_house_price_index_series"),
        sa.CheckConstraint("quarter BETWEEN 1 AND 4", name="ck_house_price_index_quarter"),
        sa.PrimaryKeyConstraint("series", "geo_code", "year", "quarter"),
    )

    op.create_table(
        "hpi_refresh_status",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("last_attempt_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_success_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("latest_year", sa.Integer(), nullable=True),
        sa.Column("latest_quarter", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_hpi_refresh_status_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )

    for table in ("expenses", "recurring_expenses"):
        op.add_column(table, sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.add_column(table, sa.Column("asset_role", sa.String(length=20), nullable=True))
        op.create_foreign_key(f"fk_{table}_asset_id", table, "assets", ["asset_id"], ["id"], ondelete="SET NULL")
        op.create_check_constraint(f"ck_{table}_asset_role", table, _ROLE_CHECK)
        op.create_check_constraint(f"ck_{table}_asset_role_requires_asset", table, _ROLE_REQUIRES_ASSET_CHECK)
        op.create_index(f"idx_{table}_asset", table, ["asset_id"])


def downgrade() -> None:
    for table in ("recurring_expenses", "expenses"):
        op.drop_index(f"idx_{table}_asset", table_name=table)
        op.drop_constraint(f"ck_{table}_asset_role_requires_asset", table, type_="check")
        op.drop_constraint(f"ck_{table}_asset_role", table, type_="check")
        op.drop_constraint(f"fk_{table}_asset_id", table, type_="foreignkey")
        op.drop_column(table, "asset_role")
        op.drop_column(table, "asset_id")

    op.drop_table("hpi_refresh_status")
    op.drop_table("house_price_index")
    op.drop_index("idx_asset_contributions_asset", table_name="asset_contributions")
    op.drop_table("asset_contributions")
    op.drop_table("asset_valuations")
    op.drop_table("asset_loan_balance_corrections")
    op.drop_table("asset_loans")
    op.drop_index("idx_assets_family", table_name="assets")
    op.drop_table("assets")
