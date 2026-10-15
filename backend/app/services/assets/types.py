"""Lightweight inputs for the pure asset math.

These mirror the ORM columns the math needs, so a caller can build them straight
from model rows without the math importing SQLAlchemy. Money is integer cents;
rates are ``Decimal`` (0.0625 means 6.25%).
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

_CENT = Decimal(1)


def round_cents(value: Decimal) -> int:
    """Round a Decimal amount of cents to an integer, halves rounding up."""
    return int(value.quantize(_CENT, rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class AssetInput:
    asset_type: str  # "house" | "vehicle" | "other"
    purchase_date: date
    purchase_price_cents: int
    down_payment_cents: int = 0
    closing_costs_cents: int = 0
    state: str | None = None
    zip_code: str | None = None
    annual_depreciation_rate: Decimal | None = None
    sold_date: date | None = None
    sale_price_cents: int | None = None
    selling_costs_cents: int | None = None


@dataclass(frozen=True)
class LoanInput:
    original_amount_cents: int
    annual_interest_rate: Decimal
    term_months: int
    first_payment_date: date
    monthly_payment_cents: int | None = None
    escrow_monthly_cents: int = 0


@dataclass(frozen=True)
class CorrectionInput:
    as_of_date: date
    balance_cents: int


@dataclass(frozen=True)
class ValuationInput:
    as_of_date: date
    value_cents: int


@dataclass(frozen=True)
class ContributionInput:
    contribution_date: date
    amount_cents: int
    role: str  # "improvement" | "maintenance" | "carrying_cost"


@dataclass(frozen=True)
class LinkedExpenseInput:
    expense_date: date
    amount_cents: int
    role: str  # "loan_payment" | "improvement" | "maintenance" | "carrying_cost"


class IndexLookup(Protocol):
    """Read access to the FHFA house price index (quarterly, NSA)."""

    def get(self, series: str, geo_code: str, year: int, quarter: int) -> Decimal | None:
        """Index value for one quarter, or None when absent."""
        ...

    def latest(self, series: str, geo_code: str) -> tuple[int, int] | None:
        """Latest (year, quarter) available for a series/geo, or None when it has no data."""
        ...
