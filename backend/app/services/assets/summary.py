"""Asset totals and history: market value, loan balance, equity and cash invested.

Buckets (all integer cents):

- equity_building = down_payment + principal_paid + improvements
- sunk_cost       = interest_paid + escrow_paid + closing_costs + maintenance + carrying_cost
- cash_in         = equity_building + sunk_cost
- equity          = market_value - loan_balance

The amortization schedule is authoritative for principal, interest and escrow over the
whole loan, so linked expenses with the ``loan_payment`` role are ignored here.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.services.assets.amortization import LoanState, Schedule, build_schedule, month_end_points
from app.services.assets.types import (
    AssetInput,
    ContributionInput,
    CorrectionInput,
    LinkedExpenseInput,
    LoanInput,
    ValuationInput,
)
from app.services.assets.valuation import ValuationProvider, market_value_as_of

_COST_ROLES = ("improvement", "maintenance", "carrying_cost")


@dataclass(frozen=True)
class AssetBuckets:
    down_payment_cents: int
    principal_paid_cents: int
    improvements_cents: int
    interest_paid_cents: int
    escrow_paid_cents: int
    closing_costs_cents: int
    maintenance_cents: int
    carrying_cost_cents: int

    @property
    def equity_building_cents(self) -> int:
        return self.down_payment_cents + self.principal_paid_cents + self.improvements_cents

    @property
    def sunk_cost_cents(self) -> int:
        return (
            self.interest_paid_cents
            + self.escrow_paid_cents
            + self.closing_costs_cents
            + self.maintenance_cents
            + self.carrying_cost_cents
        )

    @property
    def cash_in_cents(self) -> int:
        return self.equity_building_cents + self.sunk_cost_cents


@dataclass(frozen=True)
class AssetSummary:
    as_of: date
    is_sold: bool
    market_value_cents: int
    loan_balance_cents: int
    equity_cents: int
    buckets: AssetBuckets
    equity_building_cents: int
    sunk_cost_cents: int
    cash_in_cents: int
    net_gain_cents: int | None  # only once sold
    valuation_source: str
    valuation_label: str | None
    loan_state: LoanState | None


@dataclass(frozen=True)
class HistoryPoint:
    date: date
    market_value_cents: int
    loan_balance_cents: int
    equity_cents: int
    cash_in_cents: int


@dataclass(frozen=True)
class _CostItem:
    on: date
    role: str
    amount_cents: int


def _cost_items(
    linked_expenses: Sequence[LinkedExpenseInput], contributions: Sequence[ContributionInput]
) -> list[_CostItem]:
    items = [_CostItem(e.expense_date, e.role, e.amount_cents) for e in linked_expenses if e.role in _COST_ROLES]
    items += [_CostItem(c.contribution_date, c.role, c.amount_cents) for c in contributions if c.role in _COST_ROLES]
    return items


def _as_of(asset: AssetInput, today: date) -> date:
    return min(today, asset.sold_date or today)


def _buckets(asset: AssetInput, loan_state: LoanState | None, items: Sequence[_CostItem], d: date) -> AssetBuckets:
    by_role = {role: 0 for role in _COST_ROLES}
    for item in items:
        if item.on <= d:
            by_role[item.role] += item.amount_cents
    return AssetBuckets(
        down_payment_cents=asset.down_payment_cents,
        principal_paid_cents=loan_state.principal_paid_cents if loan_state else 0,
        improvements_cents=by_role["improvement"],
        interest_paid_cents=loan_state.interest_paid_cents if loan_state else 0,
        escrow_paid_cents=loan_state.escrow_paid_cents if loan_state else 0,
        closing_costs_cents=asset.closing_costs_cents,
        maintenance_cents=by_role["maintenance"],
        carrying_cost_cents=by_role["carrying_cost"],
    )


def _schedule(loan: LoanInput | None, corrections: Sequence[CorrectionInput]) -> Schedule | None:
    return build_schedule(loan, corrections) if loan is not None else None


def asset_summary(
    asset: AssetInput,
    loan: LoanInput | None,
    corrections: Sequence[CorrectionInput],
    valuations: Sequence[ValuationInput],
    contributions: Sequence[ContributionInput],
    linked_expenses: Sequence[LinkedExpenseInput],
    provider: ValuationProvider,
    today: date,
) -> AssetSummary:
    as_of = _as_of(asset, today)
    schedule = _schedule(loan, corrections)
    loan_state = schedule.state_as_of(as_of) if schedule else None
    buckets = _buckets(asset, loan_state, _cost_items(linked_expenses, contributions), as_of)
    market = market_value_as_of(asset, valuations, provider, as_of)
    loan_balance = loan_state.balance_cents if loan_state else 0

    is_sold = asset.sold_date is not None and asset.sold_date <= today
    net_gain = None
    if is_sold and asset.sale_price_cents is not None:
        net_gain = asset.sale_price_cents - (asset.selling_costs_cents or 0) - loan_balance - buckets.cash_in_cents

    return AssetSummary(
        as_of=as_of,
        is_sold=is_sold,
        market_value_cents=market.value_cents,
        loan_balance_cents=loan_balance,
        equity_cents=market.value_cents - loan_balance,
        buckets=buckets,
        equity_building_cents=buckets.equity_building_cents,
        sunk_cost_cents=buckets.sunk_cost_cents,
        cash_in_cents=buckets.cash_in_cents,
        net_gain_cents=net_gain,
        valuation_source=market.source,
        valuation_label=market.as_of_label,
        loan_state=loan_state,
    )


def asset_history(
    asset: AssetInput,
    loan: LoanInput | None,
    corrections: Sequence[CorrectionInput],
    valuations: Sequence[ValuationInput],
    contributions: Sequence[ContributionInput],
    linked_expenses: Sequence[LinkedExpenseInput],
    provider: ValuationProvider,
    today: date,
) -> list[HistoryPoint]:
    """Monthly points from the purchase month to the as-of month; the last point is the as-of date itself."""
    schedule = _schedule(loan, corrections)
    items = _cost_items(linked_expenses, contributions)
    points: list[HistoryPoint] = []
    for d in month_end_points(asset.purchase_date, _as_of(asset, today)):
        loan_state = schedule.state_as_of(d) if schedule else None
        loan_balance = loan_state.balance_cents if loan_state else 0
        market_value = market_value_as_of(asset, valuations, provider, d).value_cents
        points.append(
            HistoryPoint(
                date=d,
                market_value_cents=market_value,
                loan_balance_cents=loan_balance,
                equity_cents=market_value - loan_balance,
                cash_in_cents=_buckets(asset, loan_state, items, d).cash_in_cents,
            )
        )
    return points
