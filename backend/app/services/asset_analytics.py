"""Adapters between asset rows and the pure asset math in :mod:`app.services.assets`.

The math takes plain dataclasses and an :class:`~app.services.assets.types.IndexLookup`. This module
builds those from ORM rows and loads the house price index once per request: every (series, region)
the assets need is read in a single query and then served from a dict, so a summary or a monthly
history never queries once per quarter.
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.models.asset import Asset, AssetLoan, AssetLoanBalanceCorrection
from app.ports.read_models import AssetExpenseLink
from app.ports.unit_of_work import UnitOfWork
from app.services.asset_service import AssetDetailData
from app.services.assets.amortization import loan_state_as_of
from app.services.assets.summary import AssetSummary, HistoryPoint, asset_history, asset_summary
from app.services.assets.types import (
    AssetInput,
    ContributionInput,
    CorrectionInput,
    LinkedExpenseInput,
    LoanInput,
    ValuationInput,
)
from app.services.assets.valuation import DefaultValuationProvider
from app.services.recurring_service import family_today


class PreloadedIndex:
    """An in-memory :class:`~app.services.assets.types.IndexLookup` over already-loaded series."""

    def __init__(self, series: Mapping[tuple[str, str], Mapping[tuple[int, int], Decimal]]) -> None:
        self._series = series

    def get(self, series: str, geo_code: str, year: int, quarter: int) -> Decimal | None:
        return self._series.get((series, geo_code), {}).get((year, quarter))

    def latest(self, series: str, geo_code: str) -> tuple[int, int] | None:
        quarters = self._series.get((series, geo_code))
        return max(quarters, default=None) if quarters else None


async def load_index(uow: UnitOfWork, assets: Iterable[Asset]) -> PreloadedIndex:
    """Load the ZIP3 and state series the given houses are valued from, once each."""
    keys: set[tuple[str, str]] = set()
    for asset in assets:
        if asset.asset_type != "house":
            continue
        if asset.zip_code:
            keys.add(("zip3", asset.zip_code[:3]))
        if asset.state:
            keys.add(("state", asset.state))
    loaded: dict[tuple[str, str], dict[tuple[int, int], Decimal]] = {}
    for series, geo_code in sorted(keys):
        rows = await uow.hpi.get_series(series, geo_code)
        loaded[(series, geo_code)] = {(r.year, r.quarter): r.index_value for r in rows}
    return PreloadedIndex(loaded)


def asset_input(asset: Asset) -> AssetInput:
    return AssetInput(
        asset_type=asset.asset_type,
        purchase_date=asset.purchase_date,
        purchase_price_cents=asset.purchase_price_cents,
        down_payment_cents=asset.down_payment_cents,
        closing_costs_cents=asset.closing_costs_cents,
        state=asset.state,
        zip_code=asset.zip_code,
        annual_depreciation_rate=asset.annual_depreciation_rate,
        sold_date=asset.sold_date,
        sale_price_cents=asset.sale_price_cents,
        selling_costs_cents=asset.selling_costs_cents,
    )


def loan_input(loan: AssetLoan) -> LoanInput:
    return LoanInput(
        original_amount_cents=loan.original_amount_cents,
        annual_interest_rate=loan.annual_interest_rate,
        term_months=loan.term_months,
        first_payment_date=loan.first_payment_date,
        monthly_payment_cents=loan.monthly_payment_cents,
        escrow_monthly_cents=loan.escrow_monthly_cents,
    )


def correction_inputs(corrections: Sequence[AssetLoanBalanceCorrection]) -> list[CorrectionInput]:
    return [CorrectionInput(c.as_of_date, c.balance_cents) for c in corrections]


def linked_expense_inputs(links: Iterable[AssetExpenseLink]) -> list[LinkedExpenseInput]:
    return [
        LinkedExpenseInput(e.expense_date, e.amount_cents, e.asset_role) for e in links if e.entry_type == "expense"
    ]


def loan_projection(
    loan: AssetLoan, corrections: Sequence[AssetLoanBalanceCorrection], today: date
) -> tuple[int, date | None]:
    """The loan's monthly principal-and-interest payment in force on ``today``, and its estimated payoff date."""
    state = loan_state_as_of(loan_input(loan), correction_inputs(corrections), today)
    return state.monthly_payment_cents, state.payoff_date_estimate


@dataclass(frozen=True)
class _MathInputs:
    asset: AssetInput
    loan: LoanInput | None
    corrections: list[CorrectionInput]
    valuations: list[ValuationInput]
    contributions: list[ContributionInput]
    linked_expenses: list[LinkedExpenseInput]


def _math_inputs(data: AssetDetailData, expenses: Iterable[AssetExpenseLink]) -> _MathInputs:
    return _MathInputs(
        asset=asset_input(data.asset),
        loan=loan_input(data.loan) if data.loan is not None else None,
        corrections=correction_inputs(data.corrections),
        valuations=[ValuationInput(v.as_of_date, v.value_cents) for v in data.valuations],
        contributions=[ContributionInput(c.contribution_date, c.amount_cents, c.role) for c in data.contributions],
        linked_expenses=linked_expense_inputs(expenses),
    )


def summarize(
    data: AssetDetailData, expenses: Iterable[AssetExpenseLink], index: PreloadedIndex, today: date
) -> AssetSummary:
    """Headline numbers and buckets for one asset as of ``today`` (or its sale date, once sold)."""
    i = _math_inputs(data, expenses)
    return asset_summary(
        i.asset,
        i.loan,
        i.corrections,
        i.valuations,
        i.contributions,
        i.linked_expenses,
        DefaultValuationProvider(index),
        today,
    )


def history(
    data: AssetDetailData, expenses: Iterable[AssetExpenseLink], index: PreloadedIndex, today: date
) -> list[HistoryPoint]:
    """Month-end points from the purchase month to ``today`` (or the sale date)."""
    i = _math_inputs(data, expenses)
    return asset_history(
        i.asset,
        i.loan,
        i.corrections,
        i.valuations,
        i.contributions,
        i.linked_expenses,
        DefaultValuationProvider(index),
        today,
    )


async def today_for_family(uow: UnitOfWork, family_id: uuid.UUID) -> date:
    """Today's date in the family's timezone."""
    family = await uow.families.get(family_id)
    assert family is not None  # callers sit behind require_family_member
    return family_today(family.timezone)
