from datetime import date
from decimal import Decimal
from typing import Any

from app.services.assets.amortization import loan_state_as_of
from app.services.assets.summary import asset_history, asset_summary
from app.services.assets.types import (
    AssetInput,
    ContributionInput,
    CorrectionInput,
    LinkedExpenseInput,
    LoanInput,
    ValuationInput,
)
from app.services.assets.valuation import Factor, FlatValuationProvider


class FixedFactorProvider:
    def __init__(self, ratio: str, source: str = "fhfa_zip3", label: str | None = "FHFA ZIP3 275 · 2024Q1"):
        self._factor = Factor(Decimal(ratio), source, label)

    def factor(self, asset, from_date, to_date):
        return self._factor


def make_asset(**overrides) -> AssetInput:
    values: dict[str, Any] = dict(
        asset_type="house",
        purchase_date=date(2024, 1, 15),
        purchase_price_cents=40_000_000,
        down_payment_cents=8_000_000,
        closing_costs_cents=1_000_000,
    )
    values.update(overrides)
    return AssetInput(**values)


def make_loan(**overrides) -> LoanInput:
    values: dict[str, Any] = dict(
        original_amount_cents=32_000_000,
        annual_interest_rate=Decimal("0.06"),
        term_months=360,
        first_payment_date=date(2024, 3, 1),
        escrow_monthly_cents=50_000,
    )
    values.update(overrides)
    return LoanInput(**values)


def summarize(asset, *, loan=None, corrections=(), valuations=(), contributions=(), expenses=(), provider=None, today):
    return asset_summary(
        asset, loan, corrections, valuations, contributions, expenses, provider or FlatValuationProvider(), today
    )


class TestSummaryWithoutLoan:
    def test_cash_purchase_on_purchase_date(self):
        s = summarize(make_asset(down_payment_cents=40_000_000), today=date(2024, 1, 15))
        assert s.market_value_cents == 40_000_000
        assert s.loan_balance_cents == 0
        assert s.equity_cents == 40_000_000
        assert s.buckets.down_payment_cents == 40_000_000
        assert s.buckets.closing_costs_cents == 1_000_000
        assert s.equity_building_cents == 40_000_000
        assert s.sunk_cost_cents == 1_000_000
        assert s.cash_in_cents == 41_000_000
        assert s.net_gain_cents is None
        assert s.is_sold is False
        assert s.loan_state is None

    def test_valuation_source_and_label_come_from_market_value(self):
        s = summarize(make_asset(), provider=FixedFactorProvider("1.25"), today=date(2025, 1, 15))
        assert s.market_value_cents == 50_000_000
        assert s.valuation_source == "fhfa_zip3"
        assert s.valuation_label == "FHFA ZIP3 275 · 2024Q1"

    def test_manual_valuation_overrides_the_provider_anchor(self):
        valuations = [ValuationInput(date(2024, 6, 1), 45_000_000)]
        s = summarize(make_asset(), valuations=valuations, today=date(2025, 1, 15))
        assert s.market_value_cents == 45_000_000
        assert s.valuation_source == "manual"


class TestSummaryWithLoan:
    def test_loan_buckets_come_from_the_schedule(self):
        asset, loan = make_asset(), make_loan()
        today = date(2025, 3, 1)
        state = loan_state_as_of(loan, [], today)
        s = summarize(asset, loan=loan, today=today)
        assert state.payments_made == 13
        assert s.loan_balance_cents == state.balance_cents
        assert s.equity_cents == 40_000_000 - state.balance_cents
        assert s.buckets.principal_paid_cents == state.principal_paid_cents
        assert s.buckets.interest_paid_cents == state.interest_paid_cents
        assert s.buckets.escrow_paid_cents == 13 * 50_000
        assert s.equity_building_cents == 8_000_000 + state.principal_paid_cents
        assert s.sunk_cost_cents == state.interest_paid_cents + 13 * 50_000 + 1_000_000
        assert s.cash_in_cents == s.equity_building_cents + s.sunk_cost_cents
        assert s.loan_state == state

    def test_corrections_flow_through_to_balance_and_principal(self):
        asset, loan = make_asset(), make_loan()
        correction = CorrectionInput(date(2025, 1, 10), 29_000_000)
        s = summarize(asset, loan=loan, corrections=[correction], today=date(2025, 1, 10))
        assert s.loan_balance_cents == 29_000_000
        assert s.buckets.principal_paid_cents == 3_000_000

    def test_loan_payment_expenses_are_ignored(self):
        asset, loan = make_asset(), make_loan()
        today = date(2025, 3, 1)
        payments = [LinkedExpenseInput(date(2024, m, 1), 250_000, "loan_payment") for m in range(3, 13)]
        assert summarize(asset, loan=loan, expenses=payments, today=today) == summarize(asset, loan=loan, today=today)


class TestLinkedExpensesAndContributions:
    def test_roles_land_in_their_buckets(self):
        expenses = [
            LinkedExpenseInput(date(2024, 5, 1), 1_000_00, "improvement"),
            LinkedExpenseInput(date(2024, 5, 2), 200_00, "maintenance"),
            LinkedExpenseInput(date(2024, 5, 3), 300_00, "carrying_cost"),
            LinkedExpenseInput(date(2024, 5, 4), 400_00, "maintenance"),
        ]
        s = summarize(make_asset(), expenses=expenses, today=date(2024, 6, 1))
        assert s.buckets.improvements_cents == 100_000
        assert s.buckets.maintenance_cents == 60_000
        assert s.buckets.carrying_cost_cents == 30_000
        assert s.equity_building_cents == 8_000_000 + 100_000
        assert s.sunk_cost_cents == 1_000_000 + 60_000 + 30_000

    def test_items_after_as_of_are_excluded(self):
        expenses = [LinkedExpenseInput(date(2024, 6, 2), 100_00, "maintenance")]
        contributions = [ContributionInput(date(2024, 6, 2), 500_00, "improvement")]
        s = summarize(make_asset(), expenses=expenses, contributions=contributions, today=date(2024, 6, 1))
        assert s.buckets.maintenance_cents == 0
        assert s.buckets.improvements_cents == 0

    def test_item_on_as_of_date_is_included(self):
        expenses = [LinkedExpenseInput(date(2024, 6, 1), 100_00, "maintenance")]
        assert summarize(make_asset(), expenses=expenses, today=date(2024, 6, 1)).buckets.maintenance_cents == 10_000

    def test_historical_contributions_count_in_totals(self):
        contributions = [
            ContributionInput(date(2023, 1, 1), 2_000_00, "improvement"),
            ContributionInput(date(2023, 6, 1), 150_00, "carrying_cost"),
        ]
        s = summarize(make_asset(), contributions=contributions, today=date(2024, 6, 1))
        assert s.buckets.improvements_cents == 200_000
        assert s.buckets.carrying_cost_cents == 15_000
        assert s.cash_in_cents == 8_000_000 + 1_000_000 + 200_000 + 15_000


class TestSold:
    def sold_asset(self, **overrides):
        values = dict(sold_date=date(2025, 1, 15), sale_price_cents=50_000_000, selling_costs_cents=2_500_000)
        values.update(overrides)
        return make_asset(**values)

    def test_everything_is_frozen_at_the_sale_date(self):
        asset, loan = self.sold_asset(), make_loan()
        frozen = summarize(asset, loan=loan, today=date(2025, 1, 15))
        later = summarize(
            asset,
            loan=loan,
            today=date(2026, 6, 1),
            expenses=[LinkedExpenseInput(date(2025, 6, 1), 100_00, "maintenance")],
        )
        assert later == frozen
        assert later.as_of == date(2025, 1, 15)
        assert later.market_value_cents == 50_000_000
        assert later.valuation_source == "sale_price"
        assert later.is_sold is True

    def test_net_gain_is_sale_less_costs_loan_balance_and_cash_in(self):
        asset, loan = self.sold_asset(), make_loan()
        s = summarize(asset, loan=loan, today=date(2026, 6, 1))
        state = loan_state_as_of(loan, [], date(2025, 1, 15))
        assert s.net_gain_cents == 50_000_000 - 2_500_000 - state.balance_cents - s.cash_in_cents
        assert s.equity_cents == 50_000_000 - state.balance_cents

    def test_net_gain_without_loan_or_selling_costs(self):
        asset = self.sold_asset(selling_costs_cents=None)
        s = summarize(asset, today=date(2026, 6, 1))
        assert s.net_gain_cents == 50_000_000 - (8_000_000 + 1_000_000)

    def test_future_dated_sale_is_not_sold_yet(self):
        s = summarize(self.sold_asset(), today=date(2024, 12, 1))
        assert s.is_sold is False
        assert s.net_gain_cents is None
        assert s.as_of == date(2024, 12, 1)
        assert s.market_value_cents == 40_000_000  # still the estimate, not the sale price


class TestHistory:
    def history(
        self,
        asset=None,
        *,
        loan=None,
        corrections=(),
        valuations=(),
        contributions=(),
        expenses=(),
        today,
        provider=None,
    ):
        return asset_history(
            asset or make_asset(),
            loan,
            corrections,
            valuations,
            contributions,
            expenses,
            provider or FlatValuationProvider(),
            today,
        )

    def test_points_are_month_ends_from_purchase_month_with_last_point_at_as_of(self):
        points = self.history(today=date(2024, 4, 10))
        assert [p.date for p in points] == [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31), date(2024, 4, 10)]

    def test_no_points_before_purchase(self):
        assert self.history(today=date(2024, 1, 1)) == []

    def test_equity_is_market_value_less_loan_balance(self):
        loan = make_loan()
        for p in self.history(loan=loan, today=date(2025, 6, 20), provider=FixedFactorProvider("1.1")):
            assert p.equity_cents == p.market_value_cents - p.loan_balance_cents
            assert p.loan_balance_cents == loan_state_as_of(loan, [], p.date).balance_cents

    def test_cash_in_accumulates_over_time(self):
        loan = make_loan()
        expenses = [LinkedExpenseInput(date(2024, 5, 20), 100_000, "improvement")]
        contributions = [ContributionInput(date(2024, 4, 5), 20_000, "maintenance")]
        points = {
            p.date: p
            for p in self.history(loan=loan, expenses=expenses, contributions=contributions, today=date(2024, 6, 30))
        }
        jan, mar, apr, may = (
            points[date(2024, 1, 31)],
            points[date(2024, 3, 31)],
            points[date(2024, 4, 30)],
            points[date(2024, 5, 31)],
        )
        assert jan.cash_in_cents == 9_000_000  # down payment + closing costs, no payments yet
        march_state = loan_state_as_of(loan, [], date(2024, 3, 31))
        assert (
            mar.cash_in_cents == 9_000_000 + march_state.principal_paid_cents + march_state.interest_paid_cents + 50_000
        )
        apr_state = loan_state_as_of(loan, [], date(2024, 4, 30))
        assert (
            apr.cash_in_cents
            == 9_000_000 + apr_state.principal_paid_cents + apr_state.interest_paid_cents + 100_000 + 20_000
        )
        may_state = loan_state_as_of(loan, [], date(2024, 5, 31))
        assert may.cash_in_cents == (
            9_000_000 + may_state.principal_paid_cents + may_state.interest_paid_cents + 150_000 + 20_000 + 100_000
        )

    def test_loan_payment_expenses_do_not_change_history(self):
        loan = make_loan()
        noise = [LinkedExpenseInput(date(2024, 4, 1), 300_000, "loan_payment")]
        assert self.history(loan=loan, expenses=noise, today=date(2024, 8, 1)) == self.history(
            loan=loan, today=date(2024, 8, 1)
        )

    def test_last_point_matches_the_summary(self):
        asset, loan = make_asset(), make_loan()
        expenses = [LinkedExpenseInput(date(2024, 9, 9), 12_345, "maintenance")]
        today = date(2025, 2, 14)
        last = self.history(asset, loan=loan, expenses=expenses, today=today, provider=FixedFactorProvider("1.07"))[-1]
        s = summarize(asset, loan=loan, expenses=expenses, today=today, provider=FixedFactorProvider("1.07"))
        assert last.date == today
        assert (last.market_value_cents, last.loan_balance_cents, last.equity_cents, last.cash_in_cents) == (
            s.market_value_cents,
            s.loan_balance_cents,
            s.equity_cents,
            s.cash_in_cents,
        )

    def test_sold_asset_history_ends_at_sale_with_sale_price(self):
        asset = make_asset(sold_date=date(2024, 3, 20), sale_price_cents=45_000_000, selling_costs_cents=0)
        points = self.history(asset, today=date(2026, 1, 1))
        assert points[-1].date == date(2024, 3, 20)
        assert points[-1].market_value_cents == 45_000_000
        assert points[-2].market_value_cents == 40_000_000
