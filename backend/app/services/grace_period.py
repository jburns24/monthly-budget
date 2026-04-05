"""Grace period utility: determine whether a given month is still editable."""

from datetime import datetime, timezone
from typing import Protocol
from zoneinfo import ZoneInfo


class FamilyGracePeriod(Protocol):
    """Protocol for the family attributes required by grace period logic.

    Any object providing ``timezone`` (IANA tz string) and
    ``edit_grace_days`` (int) satisfies this protocol.
    """

    timezone: str
    edit_grace_days: int


def _now_utc() -> datetime:
    """Return the current UTC time. Extracted for easy mocking in tests."""
    return datetime.now(tz=timezone.utc)


def is_within_grace_period(family: FamilyGracePeriod, year_month: str) -> bool:
    """Return True if *year_month* expenses are still editable under the family's grace period.

    Rules:
    - The current month is always editable (returns True).
    - For past months, compute the number of days since the month ended (in the
      family's local timezone).  If that count is <= family.edit_grace_days the
      month is still editable.

    Parameters
    ----------
    family:
        An object with ``timezone`` (IANA tz string) and ``edit_grace_days`` (int).
        The :class:`~app.models.family.Family` ORM model satisfies this protocol.
    year_month:
        The month to check, formatted as ``"YYYY-MM"``.

    Returns
    -------
    bool
        ``True`` if the month is within the grace period (editable),
        ``False`` otherwise.
    """
    tz = ZoneInfo(family.timezone)
    now_local = _now_utc().astimezone(tz)

    # Parse the requested month
    year, month = map(int, year_month.split("-"))

    # Current month is always editable
    if now_local.year == year and now_local.month == month:
        return True

    # Future months are treated as editable (shouldn't normally happen, but safe)
    if (year, month) > (now_local.year, now_local.month):
        return True

    # Compute the first instant of the month *after* year_month in local tz.
    # That instant is "month-end" — the moment the month stopped.
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    # Midnight of the first day of the next month in local tz = end of our month
    month_end_local = datetime(next_year, next_month, 1, 0, 0, 0, tzinfo=tz)

    # Number of whole days since the month ended
    delta = now_local - month_end_local
    days_since_end = delta.days  # negative if month hasn't ended yet (handled above)

    return days_since_end <= family.edit_grace_days
