"""Recurring expense service: configure a rule once, reconcile it into real entries on demand.

There is no scheduler. Rules are *reconciled* — every due occurrence up to "today"
(in the family's timezone) is materialised as an ordinary ``Expense`` — when a
user-initiated request asks for the budget summary, and immediately after a rule
is created or resumed. Reconciliation is idempotent: ``next_due_date`` advances as
rows are generated, ``lock_due`` serialises concurrent requests, and a unique
index on (recurring_expense_id, expense_date) is the final backstop.
"""

import calendar
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.logging import get_logger
from app.models.expense import Expense
from app.models.recurring_expense import RecurringExpense
from app.ports.unit_of_work import UnitOfWork
from app.services.expense_service import _validate_category

logger = get_logger(__name__)

# Safety valve for a rule left untouched for years; the remainder is picked up by
# the next reconciliation rather than blocking this request.
MAX_OCCURRENCES_PER_RULE = 400


def _add_months(start: date, months: int) -> date:
    """``start`` shifted by ``months``, clamped to the last day of a short month."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def occurrence_date(start_date: date, frequency: str, index: int) -> date:
    """The ``index``-th (0-based) occurrence of a rule anchored on ``start_date``.

    Derived from the anchor rather than stepped from the previous occurrence, so a
    monthly rule starting on the 31st returns to the 31st after a short month.
    """
    if frequency == "weekly":
        return start_date + timedelta(weeks=index)
    if frequency == "biweekly":
        return start_date + timedelta(weeks=2 * index)
    if frequency == "monthly":
        return _add_months(start_date, index)
    if frequency == "yearly":
        return _add_months(start_date, 12 * index)
    raise ValueError(f"unknown frequency {frequency!r}")


def family_today(timezone_name: str) -> date:
    """Today's date in the family's local timezone."""
    return datetime.now(tz=ZoneInfo(timezone_name)).date()


def _fast_forward(rule: RecurringExpense, today: date) -> None:
    """Skip occurrences before ``today`` without generating them (resuming a paused rule)."""
    while rule.next_due_date < today:
        rule.occurrences_created += 1
        rule.next_due_date = occurrence_date(rule.start_date, rule.frequency, rule.occurrences_created)


async def list_rules(uow: UnitOfWork, family_id: uuid.UUID) -> list[RecurringExpense]:
    return await uow.recurring.list_for_family(family_id)


async def _get_rule(uow: UnitOfWork, family_id: uuid.UUID, rule_id: uuid.UUID) -> RecurringExpense:
    rule = await uow.recurring.get_in_family(rule_id, family_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Recurring expense not found")
    return rule


async def create_rule(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    category_id: uuid.UUID | None,
    amount_cents: int,
    description: str,
    entry_type: str,
    frequency: str,
    start_date: date,
    end_date: date | None,
    today: date,
) -> RecurringExpense:
    """Create a rule and reconcile it, so occurrences on or before ``today`` appear at once.

    Raises HTTPException(400) if an expense category is invalid.
    """
    if entry_type == "expense":
        if category_id is None:
            raise HTTPException(status_code=400, detail="expense requires category_id")
        await _validate_category(uow, family_id, category_id)
    else:
        category_id = None

    rule = RecurringExpense(
        family_id=family_id,
        user_id=user_id,
        category_id=category_id,
        amount_cents=amount_cents,
        description=description,
        entry_type=entry_type,
        frequency=frequency,
        start_date=start_date,
        end_date=end_date,
        next_due_date=start_date,
        occurrences_created=0,
        is_active=True,
    )
    uow.recurring.add(rule)
    await uow.flush()
    logger.info(
        "recurring_expense_created",
        rule_id=str(rule.id),
        family_id=str(family_id),
        frequency=frequency,
        entry_type=entry_type,
        amount_cents=amount_cents,
    )
    await reconcile(uow, family_id, today)
    return rule


async def update_rule(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    rule_id: uuid.UUID,
    *,
    fields: dict[str, Any],
    today: date,
) -> RecurringExpense:
    """Apply the fields present in ``fields`` (so ``end_date: None`` can clear it).

    Changing the frequency or ``next_due_date`` re-anchors the schedule on the (new)
    next due date; a new next due date must be after today, because earlier dates
    may already have generated entries. Extending the end date of a rule that had
    ended brings it back to life. Resuming a paused rule skips the periods it was
    paused for instead of back-filling them. Already-generated entries are never
    touched.
    """
    rule = await _get_rule(uow, family_id, rule_id)
    was_active = rule.is_active
    was_ended = not was_active and rule.end_date is not None and rule.next_due_date > rule.end_date

    new_category_id = fields.get("category_id")
    if new_category_id is not None:
        if rule.entry_type == "income":
            raise HTTPException(status_code=400, detail="income must not have category_id")
        await _validate_category(uow, family_id, new_category_id)

    new_next = fields.get("next_due_date")
    if new_next is not None and new_next <= today:
        raise HTTPException(status_code=400, detail="next_due_date must be after today")
    effective_next = new_next or rule.next_due_date
    effective_end = fields["end_date"] if "end_date" in fields else rule.end_date
    if new_next is not None and effective_end is not None and effective_end < new_next:
        raise HTTPException(status_code=400, detail="end_date must not be before next_due_date")

    if new_category_id is not None:
        rule.category_id = new_category_id
    for name in ("amount_cents", "description"):
        if fields.get(name) is not None:
            setattr(rule, name, fields[name])
    new_frequency = fields.get("frequency")
    if (new_frequency is not None and new_frequency != rule.frequency) or new_next is not None:
        if new_frequency is not None:
            rule.frequency = new_frequency
        rule.start_date = effective_next
        rule.next_due_date = effective_next
        rule.occurrences_created = 0
    if "end_date" in fields:
        if effective_end is not None and effective_end < rule.next_due_date and rule.is_active:
            # An end date already behind the next occurrence simply stops the rule.
            rule.is_active = False
        rule.end_date = effective_end

    resuming = fields.get("is_active") is True and not was_active
    if fields.get("is_active") is not None:
        rule.is_active = fields["is_active"]
    elif was_ended and (rule.end_date is None or rule.next_due_date <= rule.end_date):
        rule.is_active = True
    if resuming:
        _fast_forward(rule, today)
        if rule.end_date is not None and rule.next_due_date > rule.end_date:
            raise HTTPException(status_code=400, detail="end_date has passed; extend it to resume this rule")

    rule.updated_at = datetime.now(tz=timezone.utc)
    await uow.flush()
    logger.info("recurring_expense_updated", rule_id=str(rule_id), family_id=str(family_id), fields=list(fields))
    await reconcile(uow, family_id, today)
    return rule


async def delete_rule(uow: UnitOfWork, family_id: uuid.UUID, rule_id: uuid.UUID) -> None:
    """Delete a rule. Entries it already generated stay, detached (FK is SET NULL)."""
    rule = await _get_rule(uow, family_id, rule_id)
    await uow.recurring.delete(rule)
    await uow.flush()
    logger.info("recurring_expense_deleted", rule_id=str(rule_id), family_id=str(family_id))


async def reconcile(uow: UnitOfWork, family_id: uuid.UUID, today: date) -> int:
    """Materialise every due occurrence up to ``today``. Returns how many entries were created."""
    rules = await uow.recurring.lock_due(family_id, today)
    now = datetime.now(tz=timezone.utc)
    created = 0

    for rule in rules:
        if rule.entry_type == "expense":
            try:
                assert rule.category_id is not None  # DB CHECK guarantees it for expenses
                await _validate_category(uow, family_id, rule.category_id)
            except HTTPException:
                # Category archived: leave the rule due so it resumes once it is fixed.
                logger.warning("recurring_expense_skipped_invalid_category", rule_id=str(rule.id))
                continue

        generated = 0
        while (
            rule.next_due_date <= today
            and (rule.end_date is None or rule.next_due_date <= rule.end_date)
            and generated < MAX_OCCURRENCES_PER_RULE
        ):
            uow.expenses.add(
                Expense(
                    family_id=family_id,
                    user_id=rule.user_id,
                    category_id=rule.category_id,
                    amount_cents=rule.amount_cents,
                    description=rule.description,
                    expense_date=rule.next_due_date,
                    year_month=rule.next_due_date.strftime("%Y-%m"),
                    entry_type=rule.entry_type,
                    is_starting_balance=False,
                    recurring_expense_id=rule.id,
                    created_at=now,
                    updated_at=now,
                )
            )
            rule.occurrences_created += 1
            rule.next_due_date = occurrence_date(rule.start_date, rule.frequency, rule.occurrences_created)
            generated += 1

        if rule.end_date is not None and rule.next_due_date > rule.end_date:
            rule.is_active = False
        if generated:
            rule.updated_at = now
            created += generated

    if rules:
        await uow.flush()
    if created:
        logger.info("recurring_expenses_reconciled", family_id=str(family_id), created=created)
    return created
