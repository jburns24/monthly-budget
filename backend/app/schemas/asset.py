"""Asset request/response Pydantic schemas."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints, field_validator, model_validator

from app.schemas.expense import ExpenseResponse

AssetType = Literal["house", "vehicle", "other"]
ContributionRole = Literal["improvement", "maintenance", "carrying_cost"]

# Rates are Decimal in the domain and Python, but plain JSON numbers (0.0625) on the wire.
Rate = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]

AssetName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
StateCode = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z]{2}$")]
ZipCode = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{5}$")]


def _require_house_location(asset_type: str | None, state: str | None, zip_code: str | None) -> None:
    if asset_type == "house" and (not state or not zip_code):
        raise ValueError("a house requires state and zip_code")


# ---------------------------------------------------------------------------
# Loan
# ---------------------------------------------------------------------------


class AssetLoanInput(BaseModel):
    """Loan terms, used nested in asset creation and as the body of PUT .../loan."""

    original_amount_cents: int = Field(gt=0)
    annual_interest_rate: Rate = Field(ge=0, le=1, max_digits=7, decimal_places=5)  # 0.0625 = 6.25%
    term_months: int = Field(gt=0, le=1200)
    first_payment_date: date
    monthly_payment_cents: int | None = Field(default=None, gt=0)  # P&I; null = compute from the formula
    escrow_monthly_cents: int = Field(default=0, ge=0)


class AssetLoanResponse(BaseModel):
    """A loan. ``monthly_payment_cents`` is the stored override (null = computed from the formula)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    original_amount_cents: int
    annual_interest_rate: Rate
    term_months: int
    first_payment_date: date
    monthly_payment_cents: int | None
    escrow_monthly_cents: int
    # Principal-and-interest payment in force today (the override, or the formula) and the projected payoff.
    computed_monthly_payment_cents: int | None = None
    payoff_date_estimate: date | None = None
    created_at: datetime
    updated_at: datetime


class LoanCorrectionCreate(BaseModel):
    """Request body for POST .../loan/corrections."""

    as_of_date: date
    balance_cents: int = Field(ge=0)


class LoanCorrectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    loan_id: uuid.UUID
    as_of_date: date
    balance_cents: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Valuations and contributions
# ---------------------------------------------------------------------------


class AssetValuationCreate(BaseModel):
    """Request body for POST .../valuations (a manual, dated market value)."""

    as_of_date: date
    value_cents: int = Field(ge=0)
    note: str | None = Field(default=None, max_length=500)


class AssetValuationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    as_of_date: date
    value_cents: int
    note: str | None
    created_at: datetime


class AssetContributionCreate(BaseModel):
    """Request body for POST .../contributions (a historical amount put into the asset)."""

    contribution_date: date
    amount_cents: int = Field(gt=0)
    role: ContributionRole
    description: str = Field(default="", max_length=500)


class AssetContributionUpdate(BaseModel):
    """Request body for PUT .../contributions/{contribution_id}; only present fields change."""

    contribution_date: date | None = None
    amount_cents: int | None = Field(default=None, gt=0)
    role: ContributionRole | None = None
    description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> Self:
        for name in ("contribution_date", "amount_cents", "role", "description"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        return self


class AssetContributionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    contribution_date: date
    amount_cents: int
    role: ContributionRole
    description: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Asset
# ---------------------------------------------------------------------------


class AssetCreate(BaseModel):
    """Request body for POST /api/families/{family_id}/assets."""

    name: AssetName
    asset_type: AssetType
    purchase_date: date
    purchase_price_cents: int = Field(ge=0)
    down_payment_cents: int = Field(default=0, ge=0)
    closing_costs_cents: int = Field(default=0, ge=0)
    address_line1: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    state: StateCode | None = None
    zip_code: ZipCode | None = None
    annual_depreciation_rate: Rate | None = Field(default=None, ge=0, le=1, max_digits=5, decimal_places=4)
    loan: AssetLoanInput | None = None

    @model_validator(mode="after")
    def validate_house_location(self) -> Self:
        _require_house_location(self.asset_type, self.state, self.zip_code)
        return self


class AssetUpdate(BaseModel):
    """Request body for PUT /api/families/{family_id}/assets/{asset_id}.

    Only fields present in the body change; the nullable address and depreciation fields
    can be cleared with an explicit null. The loan, sale and valuations have their own endpoints.
    """

    name: AssetName | None = None
    asset_type: AssetType | None = None
    purchase_date: date | None = None
    purchase_price_cents: int | None = Field(default=None, ge=0)
    down_payment_cents: int | None = Field(default=None, ge=0)
    closing_costs_cents: int | None = Field(default=None, ge=0)
    address_line1: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    state: StateCode | None = None
    zip_code: ZipCode | None = None
    annual_depreciation_rate: Rate | None = Field(default=None, ge=0, le=1, max_digits=5, decimal_places=4)

    @field_validator("name", "asset_type", "purchase_date", "purchase_price_cents", mode="before")
    @classmethod
    def _reject_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("must not be null")
        return value

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> Self:
        for name in ("down_payment_cents", "closing_costs_cents"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        return self


class AssetSellRequest(BaseModel):
    """Request body for POST .../sell."""

    sold_date: date
    sale_price_cents: int = Field(ge=0)
    selling_costs_cents: int = Field(default=0, ge=0)


class AssetListSummary(BaseModel):
    """Headline numbers for an asset card, as of today (or the sale date once sold)."""

    market_value_cents: int
    loan_balance_cents: int
    equity_cents: int
    cash_in_cents: int
    valuation_source: str


class AssetDetailSummary(AssetListSummary):
    """Full breakdown for the detail page: equity-building vs sunk-cost buckets, and the net gain once sold."""

    down_payment_cents: int
    principal_paid_cents: int
    improvements_cents: int
    interest_paid_cents: int
    escrow_paid_cents: int
    closing_costs_cents: int
    maintenance_cents: int
    carrying_cost_cents: int
    equity_building_cents: int
    sunk_cost_cents: int
    net_gain_cents: int | None = None  # only once sold


class AssetValuationInfo(BaseModel):
    """Where the current market value comes from; ``label`` is e.g. ``FHFA ZIP3 276 · 2026Q1``."""

    source: str
    label: str | None = None


class HpiStatusResponse(BaseModel):
    """Latest quarter of the cached house price index (null until a refresh has succeeded)."""

    latest_year: int | None = None
    latest_quarter: int | None = None


class HpiRefreshStatusResponse(HpiStatusResponse):
    """Full refresh bookkeeping, returned by the admin refresh endpoint."""

    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None


class AssetResponse(BaseModel):
    """An asset's own fields."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    family_id: uuid.UUID
    created_by_user_id: uuid.UUID
    name: str
    asset_type: AssetType
    purchase_date: date
    purchase_price_cents: int
    down_payment_cents: int
    closing_costs_cents: int
    address_line1: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    annual_depreciation_rate: Rate | None
    sold_date: date | None
    sale_price_cents: int | None
    selling_costs_cents: int | None
    is_sold: bool
    created_at: datetime
    updated_at: datetime


class AssetListItem(AssetResponse):
    """An asset in the list, with its headline numbers."""

    has_loan: bool = False
    summary: AssetListSummary | None = None


class AssetListResponse(BaseModel):
    assets: list[AssetListItem]


class AssetDetail(AssetResponse):
    """An asset with its loan, corrections, valuations, contributions and computed summary."""

    loan: AssetLoanResponse | None
    corrections: list[LoanCorrectionResponse]
    valuations: list[AssetValuationResponse]
    contributions: list[AssetContributionResponse]
    summary: AssetDetailSummary | None = None
    valuation: AssetValuationInfo | None = None
    hpi_status: HpiStatusResponse | None = None


class AssetExpensesResponse(BaseModel):
    """Expenses linked to an asset, newest first."""

    expenses: list[ExpenseResponse]


class AssetHistoryPoint(BaseModel):
    """One month-end sample of the asset's story chart."""

    date: date
    market_value_cents: int
    loan_balance_cents: int
    equity_cents: int
    cash_in_cents: int


class AssetHistoryResponse(BaseModel):
    points: list[AssetHistoryPoint]
