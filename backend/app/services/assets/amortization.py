"""Loan amortization with balance corrections.

Payment ``k`` (1-based) falls due ``first_payment_date + (k - 1)`` months, clamping the
day to the end of shorter months. Interest accrues monthly on the running balance and is
rounded half up to cents; the final payment shrinks to whatever clears the balance.

A *correction* is a dated statement balance. It replaces the balance after the last
payment due on or before its date, and the schedule continues from there keeping the
current payment (so the term floats). If the corrected balance's monthly interest would
swallow the whole payment, the payment is re-amortized over the remaining original term.
"""

from bisect import bisect_right
from calendar import monthrange
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, Decimal, localcontext

from app.services.assets.types import CorrectionInput, LoanInput, round_cents

_MONTHS_PER_YEAR = Decimal(12)
# Safety valve for payments that never amortize (e.g. an explicit payment below the interest).
_MAX_MONTHS = 1200


def add_months(base: date, months: int) -> date:
    """``base`` shifted by whole months, clamping the day to the target month's length."""
    year, month_index = divmod(base.year * 12 + (base.month - 1) + months, 12)
    month = month_index + 1
    return date(year, month, min(base.day, monthrange(year, month)[1]))


def month_end(d: date) -> date:
    return date(d.year, d.month, monthrange(d.year, d.month)[1])


def month_end_points(start: date, end: date) -> list[date]:
    """Month-end dates from ``start``'s month through ``end``'s month; the last point is ``end`` itself."""
    if end < start:
        return []
    points: list[date] = []
    cursor = month_end(start)
    while cursor < end:
        points.append(cursor)
        cursor = month_end(add_months(cursor.replace(day=1), 1))
    points.append(end)
    return points


def _level_payment(principal_cents: int, monthly_rate: Decimal, months: int) -> int:
    """Level payment amortizing ``principal_cents`` over ``months``; zero rate is a ceiling split."""
    if monthly_rate == 0:
        return int((Decimal(principal_cents) / months).to_integral_value(rounding=ROUND_CEILING))
    with localcontext() as ctx:
        ctx.prec = 50
        factor = 1 - (1 + monthly_rate) ** -months
        return round_cents(Decimal(principal_cents) * monthly_rate / factor)


def _interest_cents(balance_cents: int, monthly_rate: Decimal) -> int:
    return round_cents(Decimal(balance_cents) * monthly_rate)


@dataclass(frozen=True)
class Payment:
    number: int
    due_date: date
    interest_cents: int
    principal_cents: int
    escrow_cents: int
    balance_after_cents: int


@dataclass(frozen=True)
class LoanState:
    balance_cents: int
    principal_paid_cents: int
    interest_paid_cents: int
    escrow_paid_cents: int
    payments_made: int
    monthly_payment_cents: int
    payoff_date_estimate: date | None


@dataclass(frozen=True)
class _Event:
    """A change to the balance (payment or correction) and the level payment in force afterwards."""

    on: date
    balance_cents: int
    payment_cents: int


@dataclass(frozen=True)
class Schedule:
    """The full projected schedule for a loan, queryable at any date."""

    original_amount_cents: int
    initial_payment_cents: int
    payments: tuple[Payment, ...]
    events: tuple[_Event, ...]
    cum_interest: tuple[int, ...]
    cum_escrow: tuple[int, ...]

    @property
    def payoff_date(self) -> date | None:
        """Date the balance reaches zero for good, or None if the schedule never clears it."""
        if self.events and self.events[-1].balance_cents == 0:
            return self.events[-1].on
        return None

    def state_as_of(self, as_of: date) -> LoanState:
        idx = bisect_right([e.on for e in self.events], as_of)
        if idx:
            balance = self.events[idx - 1].balance_cents
            payment = self.events[idx - 1].payment_cents
        else:
            balance = self.original_amount_cents
            payment = self.initial_payment_cents
        made = bisect_right([p.due_date for p in self.payments], as_of)
        return LoanState(
            balance_cents=balance,
            principal_paid_cents=max(0, self.original_amount_cents - balance),
            interest_paid_cents=self.cum_interest[made - 1] if made else 0,
            escrow_paid_cents=self.cum_escrow[made - 1] if made else 0,
            payments_made=made,
            monthly_payment_cents=payment,
            payoff_date_estimate=self.payoff_date,
        )


def build_schedule(loan: LoanInput, corrections: Sequence[CorrectionInput]) -> Schedule:
    rate = loan.annual_interest_rate / _MONTHS_PER_YEAR
    initial_payment = loan.monthly_payment_cents or _level_payment(loan.original_amount_cents, rate, loan.term_months)
    pending = deque(sorted(corrections, key=lambda c: c.as_of_date))
    balance = loan.original_amount_cents
    payment_cents = initial_payment
    payments: list[Payment] = []
    events: list[_Event] = []
    month = 0  # index of the next payment's due date
    corrected = False

    def apply_correction(correction: CorrectionInput) -> None:
        nonlocal balance, payment_cents, corrected
        corrected = True
        balance = correction.balance_cents
        if balance > 0 and _interest_cents(balance, rate) >= payment_cents:
            payment_cents = _level_payment(balance, rate, max(loan.term_months - month, 1))
        events.append(_Event(correction.as_of_date, balance, payment_cents))

    while month < _MAX_MONTHS:
        due = add_months(loan.first_payment_date, month)
        while pending and pending[0].as_of_date < due:
            apply_correction(pending.popleft())
        if balance == 0:
            if not pending:
                break
            month += 1  # paid off, but a later correction may bring a balance back
            continue
        interest = _interest_cents(balance, rate)
        principal = min(max(payment_cents - interest, 0), balance)
        if not corrected and month == loan.term_months - 1 and balance - principal <= payment_cents:
            principal = balance  # the final scheduled payment absorbs rounding drift in the level payment
        balance -= principal
        payments.append(Payment(len(payments) + 1, due, interest, principal, loan.escrow_monthly_cents, balance))
        events.append(_Event(due, balance, payment_cents))
        month += 1
    while pending:
        apply_correction(pending.popleft())

    cum_interest: list[int] = []
    cum_escrow: list[int] = []
    interest_total = escrow_total = 0
    for p in payments:
        interest_total += p.interest_cents
        escrow_total += p.escrow_cents
        cum_interest.append(interest_total)
        cum_escrow.append(escrow_total)
    return Schedule(
        original_amount_cents=loan.original_amount_cents,
        initial_payment_cents=initial_payment,
        payments=tuple(payments),
        events=tuple(events),
        cum_interest=tuple(cum_interest),
        cum_escrow=tuple(cum_escrow),
    )


def loan_state_as_of(loan: LoanInput, corrections: Sequence[CorrectionInput], as_of: date) -> LoanState:
    """Balance and paid-to-date totals as of ``as_of`` (payments due on that day count)."""
    return build_schedule(loan, corrections).state_as_of(as_of)


def monthly_series(loan: LoanInput, corrections: Sequence[CorrectionInput], dates: Sequence[date]) -> list[LoanState]:
    """Loan state at each of ``dates`` (e.g. from :func:`month_end_points`), from one schedule build."""
    schedule = build_schedule(loan, corrections)
    return [schedule.state_as_of(d) for d in dates]
