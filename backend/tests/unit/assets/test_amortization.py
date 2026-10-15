from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.services.assets.amortization import (
    add_months,
    build_schedule,
    loan_state_as_of,
    month_end_points,
    monthly_series,
)
from app.services.assets.types import CorrectionInput, LoanInput


def make_loan(**overrides) -> LoanInput:
    values: dict[str, Any] = dict(
        original_amount_cents=30_000_000,
        annual_interest_rate=Decimal("0.06"),
        term_months=360,
        first_payment_date=date(2024, 2, 1),
        monthly_payment_cents=None,
        escrow_monthly_cents=0,
    )
    values.update(overrides)
    return LoanInput(**values)


class TestAddMonths:
    def test_clamps_day_to_month_end(self):
        assert add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)

    def test_clamps_to_leap_day(self):
        assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)

    def test_counts_from_base_not_previous_clamp(self):
        assert add_months(date(2025, 1, 31), 2) == date(2025, 3, 31)

    def test_rolls_over_year(self):
        assert add_months(date(2024, 11, 15), 3) == date(2025, 2, 15)


class TestMonthlyPayment:
    def test_computed_from_formula(self):
        state = loan_state_as_of(make_loan(), [], date(2024, 2, 1))
        assert state.monthly_payment_cents == 179_865  # $1,798.65 for $300k @ 6% / 30y

    def test_zero_rate_is_ceil_of_principal_over_term(self):
        loan = make_loan(original_amount_cents=1_000_000, annual_interest_rate=Decimal("0"), term_months=12)
        state = loan_state_as_of(loan, [], date(2024, 2, 1))
        assert state.monthly_payment_cents == 83_334

    def test_explicit_payment_is_used(self):
        loan = make_loan(monthly_payment_cents=200_000)
        assert loan_state_as_of(loan, [], date(2024, 2, 1)).monthly_payment_cents == 200_000


class TestScheduleBasics:
    def test_before_first_payment_nothing_is_paid(self):
        state = loan_state_as_of(make_loan(), [], date(2024, 1, 31))
        assert state.balance_cents == 30_000_000
        assert state.payments_made == 0
        assert state.principal_paid_cents == 0
        assert state.interest_paid_cents == 0
        assert state.escrow_paid_cents == 0

    def test_first_payment_splits_interest_and_principal(self):
        state = loan_state_as_of(make_loan(), [], date(2024, 2, 1))  # due date counts
        assert state.payments_made == 1
        assert state.interest_paid_cents == 150_000
        assert state.principal_paid_cents == 29_865
        assert state.balance_cents == 29_970_135

    def test_interest_rounds_half_up(self):
        loan = make_loan(original_amount_cents=10_100, term_months=12)  # 10100 * 0.005 = 50.5
        state = loan_state_as_of(loan, [], loan.first_payment_date)
        assert state.interest_paid_cents == 51

    def test_due_dates_clamp_to_month_end(self):
        schedule = build_schedule(make_loan(first_payment_date=date(2025, 1, 31)), [])
        assert [p.due_date for p in schedule.payments[:3]] == [date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31)]

    def test_full_term_pays_off_exactly(self):
        loan = make_loan()
        end = add_months(loan.first_payment_date, 359)
        state = loan_state_as_of(loan, [], end)
        assert state.balance_cents == 0
        assert state.payments_made == 360
        assert state.principal_paid_cents == loan.original_amount_cents
        assert state.payoff_date_estimate == end

    def test_rounding_residue_is_folded_into_the_final_scheduled_payment(self):
        # a rounded level payment leaves cents of drift; the last payment absorbs it instead of adding a 361st
        for rate in ("0.0375", "0.0625", "0.0699"):
            loan = make_loan(annual_interest_rate=Decimal(rate), original_amount_cents=28_765_433)
            schedule = build_schedule(loan, [])
            assert len(schedule.payments) == 360
            assert schedule.payments[-1].balance_after_cents == 0

    def test_final_payment_is_close_to_the_level_payment(self):
        schedule = build_schedule(make_loan(), [])
        last = schedule.payments[-1]
        assert abs(last.interest_cents + last.principal_cents - 179_865) < 1_000
        assert last.balance_after_cents == 0

    def test_state_after_payoff_stays_zero(self):
        state = loan_state_as_of(make_loan(), [], date(2080, 1, 1))
        assert state.balance_cents == 0
        assert state.payments_made == 360

    def test_zero_rate_schedule_pays_off(self):
        loan = make_loan(original_amount_cents=1_000_000, annual_interest_rate=Decimal("0"), term_months=12)
        state = loan_state_as_of(loan, [], date(2025, 1, 1))
        assert state.balance_cents == 0
        assert state.payments_made == 12
        assert state.interest_paid_cents == 0

    def test_explicit_payment_shortens_the_term(self):
        loan = make_loan(monthly_payment_cents=300_000)
        state = loan_state_as_of(loan, [], date(2080, 1, 1))
        assert state.balance_cents == 0
        assert state.payments_made < 360

    def test_payment_that_never_amortizes_does_not_loop_forever(self):
        loan = make_loan(monthly_payment_cents=100)  # below monthly interest
        state = loan_state_as_of(loan, [], date(2030, 1, 1))
        assert state.balance_cents == loan.original_amount_cents
        assert state.payoff_date_estimate is None


class TestEscrow:
    def test_escrow_accrues_per_payment(self):
        loan = make_loan(escrow_monthly_cents=40_000)
        state = loan_state_as_of(loan, [], date(2024, 3, 1))
        assert state.payments_made == 2
        assert state.escrow_paid_cents == 80_000

    def test_no_escrow_after_payoff(self):
        loan = make_loan(escrow_monthly_cents=40_000)
        state = loan_state_as_of(loan, [], date(2080, 1, 1))
        assert state.escrow_paid_cents == 360 * 40_000


class TestCorrections:
    def test_correction_replaces_balance_and_keeps_payment(self):
        loan = make_loan()
        correction = CorrectionInput(as_of_date=date(2025, 1, 15), balance_cents=29_000_000)
        at_correction = loan_state_as_of(loan, [correction], date(2025, 1, 15))
        assert at_correction.balance_cents == 29_000_000
        assert at_correction.principal_paid_cents == 1_000_000
        next_payment = loan_state_as_of(loan, [correction], date(2025, 2, 1))
        # interest on corrected balance: 29,000,000 * 0.005 = 145,000
        assert next_payment.balance_cents == 29_000_000 - (179_865 - 145_000)
        assert next_payment.monthly_payment_cents == 179_865

    def test_correction_before_its_date_has_no_effect(self):
        loan = make_loan()
        correction = CorrectionInput(as_of_date=date(2025, 1, 15), balance_cents=29_000_000)
        with_correction = loan_state_as_of(loan, [correction], date(2025, 1, 14))
        without = loan_state_as_of(loan, [], date(2025, 1, 14))
        assert replace(with_correction, payoff_date_estimate=None) == replace(without, payoff_date_estimate=None)

    def test_correction_on_a_payment_date_applies_after_that_payment(self):
        loan = make_loan()
        correction = CorrectionInput(as_of_date=date(2025, 1, 1), balance_cents=29_000_000)  # payment 12 due
        state = loan_state_as_of(loan, [correction], date(2025, 1, 1))
        assert state.payments_made == 12
        assert state.balance_cents == 29_000_000

    def test_latest_correction_on_or_before_date_wins(self):
        loan = make_loan()
        first = CorrectionInput(as_of_date=date(2025, 1, 15), balance_cents=29_000_000)
        second = CorrectionInput(as_of_date=date(2025, 6, 15), balance_cents=28_000_000)
        assert loan_state_as_of(loan, [second, first], date(2025, 3, 1)).balance_cents < 29_000_000
        assert loan_state_as_of(loan, [second, first], date(2025, 6, 15)).balance_cents == 28_000_000

    def test_extra_payment_shortens_payoff(self):
        loan = make_loan()
        baseline = loan_state_as_of(loan, [], date(2024, 2, 1)).payoff_date_estimate
        correction = CorrectionInput(as_of_date=date(2025, 1, 15), balance_cents=20_000_000)
        shortened = loan_state_as_of(loan, [correction], date(2025, 1, 15)).payoff_date_estimate
        assert baseline is not None and shortened is not None
        assert shortened < baseline

    def test_interest_and_escrow_totals_count_payments_not_corrections(self):
        loan = make_loan(escrow_monthly_cents=10_000)
        correction = CorrectionInput(as_of_date=date(2024, 2, 15), balance_cents=25_000_000)
        state = loan_state_as_of(loan, [correction], date(2024, 3, 1))
        assert state.payments_made == 2
        assert state.escrow_paid_cents == 20_000
        assert state.interest_paid_cents == 150_000 + 125_000  # second payment accrues on the corrected balance

    def test_correction_before_first_payment_sets_opening_balance(self):
        loan = make_loan()
        correction = CorrectionInput(as_of_date=date(2024, 1, 10), balance_cents=29_000_000)
        assert loan_state_as_of(loan, [correction], date(2024, 1, 20)).balance_cents == 29_000_000
        assert loan_state_as_of(loan, [correction], date(2024, 2, 1)).interest_paid_cents == 145_000

    def test_correction_to_zero_ends_loan(self):
        loan = make_loan(escrow_monthly_cents=10_000)
        correction = CorrectionInput(as_of_date=date(2025, 1, 15), balance_cents=0)
        state = loan_state_as_of(loan, [correction], date(2030, 1, 1))
        assert state.balance_cents == 0
        assert state.payments_made == 12
        assert state.escrow_paid_cents == 12 * 10_000
        assert state.payoff_date_estimate == date(2025, 1, 15)

    def test_correction_after_payoff_restarts_payments(self):
        loan = make_loan(original_amount_cents=1_000_000, term_months=12, annual_interest_rate=Decimal("0"))
        correction = CorrectionInput(as_of_date=date(2026, 3, 15), balance_cents=500_000)
        assert loan_state_as_of(loan, [correction], date(2026, 3, 1)).balance_cents == 0
        assert loan_state_as_of(loan, [correction], date(2026, 3, 15)).balance_cents == 500_000
        assert loan_state_as_of(loan, [correction], date(2026, 4, 1)).balance_cents == 500_000 - 83_334

    def test_payment_is_recomputed_when_correction_makes_it_too_small(self):
        loan = make_loan(
            original_amount_cents=1_000_000, annual_interest_rate=Decimal("0.12"), term_months=12
        )  # level payment 88,849; first due 2024-02-01
        correction = CorrectionInput(as_of_date=date(2024, 2, 15), balance_cents=100_000_000)
        state = loan_state_as_of(loan, [correction], date(2024, 3, 1))
        # interest alone (1,000,000) would exceed 88,849, so the payment is re-amortized over the 11 remaining months
        assert state.monthly_payment_cents > 1_000_000
        assert state.balance_cents < 100_000_000
        final = loan_state_as_of(loan, [correction], date(2026, 1, 1))
        assert final.balance_cents == 0
        assert final.payoff_date_estimate == add_months(loan.first_payment_date, 11)


class TestSeries:
    def test_month_end_points_runs_from_start_month_to_end_with_last_point_at_end(self):
        assert month_end_points(date(2024, 1, 15), date(2024, 4, 10)) == [
            date(2024, 1, 31),
            date(2024, 2, 29),
            date(2024, 3, 31),
            date(2024, 4, 10),
        ]

    def test_month_end_points_single_month(self):
        assert month_end_points(date(2024, 4, 2), date(2024, 4, 10)) == [date(2024, 4, 10)]

    def test_month_end_points_empty_when_end_before_start(self):
        assert month_end_points(date(2024, 5, 2), date(2024, 4, 10)) == []

    def test_month_end_points_end_on_month_end(self):
        assert month_end_points(date(2024, 1, 15), date(2024, 2, 29)) == [date(2024, 1, 31), date(2024, 2, 29)]

    def test_monthly_series_matches_point_queries(self):
        loan = make_loan()
        points = month_end_points(date(2024, 1, 15), date(2024, 6, 20))
        series = monthly_series(loan, [], points)
        assert [s.balance_cents for s in series] == [loan_state_as_of(loan, [], d).balance_cents for d in points]
        assert series[0].payments_made == 0
        assert series[-1].payments_made == 5


@pytest.mark.parametrize("months", [1, 2, 11])
def test_balance_never_negative(months):
    loan = make_loan(original_amount_cents=12_345, term_months=12, annual_interest_rate=Decimal("0.0725"))
    state = loan_state_as_of(loan, [], add_months(loan.first_payment_date, months))
    assert state.balance_cents >= 0
