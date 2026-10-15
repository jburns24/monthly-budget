"""SQLAlchemy ORM models for assets and their loan, valuations and historical contributions."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

ASSET_TYPES = ("house", "vehicle", "other")
# Roles a historical contribution can play; expenses additionally allow ``loan_payment``.
ASSET_CONTRIBUTION_ROLES = ("improvement", "maintenance", "carrying_cost")


def _in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class Asset(Base):
    """Something the family owns (house, vehicle, ...) that is tracked for equity and cash put in."""

    __tablename__ = "assets"

    __table_args__ = (
        CheckConstraint(f"asset_type IN ({_in_list(ASSET_TYPES)})", name="ck_assets_asset_type"),
        CheckConstraint("purchase_price_cents >= 0", name="ck_assets_purchase_price_nonnegative"),
        CheckConstraint("down_payment_cents >= 0", name="ck_assets_down_payment_nonnegative"),
        CheckConstraint("closing_costs_cents >= 0", name="ck_assets_closing_costs_nonnegative"),
        CheckConstraint(
            "(sold_date IS NULL AND sale_price_cents IS NULL AND selling_costs_cents IS NULL) "
            "OR (sold_date IS NOT NULL AND sale_price_cents IS NOT NULL)",
            name="ck_assets_sold_fields",
        ),
        CheckConstraint("sale_price_cents IS NULL OR sale_price_cents >= 0", name="ck_assets_sale_price_nonnegative"),
        CheckConstraint(
            "selling_costs_cents IS NULL OR selling_costs_cents >= 0", name="ck_assets_selling_costs_nonnegative"
        ),
        Index("idx_assets_family", "family_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    purchase_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    down_payment_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    closing_costs_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    address_line1: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # 0.15 = 15%/yr. Used for vehicles; a null rate on a vehicle means the 15% default.
    annual_depreciation_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    sold_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sale_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selling_costs_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(tz=timezone.utc),
    )

    @property
    def is_sold(self) -> bool:
        return self.sold_date is not None


class AssetLoan(Base):
    """The (single, fixed-rate) loan financing an asset."""

    __tablename__ = "asset_loans"

    __table_args__ = (
        CheckConstraint("original_amount_cents > 0", name="ck_asset_loans_original_amount_positive"),
        CheckConstraint("term_months > 0", name="ck_asset_loans_term_positive"),
        CheckConstraint(
            "monthly_payment_cents IS NULL OR monthly_payment_cents > 0", name="ck_asset_loans_payment_positive"
        ),
        CheckConstraint("escrow_monthly_cents >= 0", name="ck_asset_loans_escrow_nonnegative"),
        UniqueConstraint("asset_id", name="uq_asset_loans_asset"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    # 0.0625 = 6.25%/yr.
    annual_interest_rate: Mapped[Decimal] = mapped_column(Numeric(7, 5), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    first_payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Principal + interest per month. Null means "compute it from the amortization formula".
    monthly_payment_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escrow_monthly_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(tz=timezone.utc),
    )


class AssetLoanBalanceCorrection(Base):
    """A dated, manually entered loan balance that re-anchors the amortization schedule."""

    __tablename__ = "asset_loan_balance_corrections"

    __table_args__ = (
        CheckConstraint("balance_cents >= 0", name="ck_asset_loan_corrections_balance_nonnegative"),
        UniqueConstraint("loan_id", "as_of_date", name="uq_asset_loan_corrections_loan_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asset_loans.id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    balance_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class AssetValuation(Base):
    """A manual, dated market value that overrides the estimated one from its date onward."""

    __tablename__ = "asset_valuations"

    __table_args__ = (
        CheckConstraint("value_cents >= 0", name="ck_asset_valuations_value_nonnegative"),
        UniqueConstraint("asset_id", "as_of_date", name="uq_asset_valuations_asset_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class AssetContribution(Base):
    """A historical amount put into an asset before tracking began. Counts in totals, never in the budget."""

    __tablename__ = "asset_contributions"

    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_asset_contributions_amount_positive"),
        CheckConstraint(f"role IN ({_in_list(ASSET_CONTRIBUTION_ROLES)})", name="ck_asset_contributions_role"),
        Index("idx_asset_contributions_asset", "asset_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    contribution_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
