"""Repository protocol for the RecurringExpense aggregate."""

from datetime import date
from typing import Protocol
from uuid import UUID

from app.models.recurring_expense import RecurringExpense


class RecurringExpenseRepository(Protocol):
    """Reads and writes for :class:`~app.models.recurring_expense.RecurringExpense`."""

    async def list_for_family(self, family_id: UUID) -> list[RecurringExpense]:
        """Return every rule for ``family_id``, newest first."""
        ...

    async def get_in_family(self, rule_id: UUID, family_id: UUID) -> RecurringExpense | None:
        """Return the rule if it exists *and* belongs to ``family_id``, else None."""
        ...

    async def lock_due(self, family_id: UUID, today: date) -> list[RecurringExpense]:
        """Return the family's active rules with ``next_due_date <= today``, locked for update.

        The lock is what keeps two concurrent reconciliations from both
        generating the same occurrence; the loser blocks until the winner's
        transaction ends and then sees the advanced ``next_due_date``. Backends
        with no concurrent writers may skip the lock.
        """
        ...

    def add(self, rule: RecurringExpense) -> None:
        """Stage a new rule. Not durable until ``UnitOfWork.flush``."""
        ...

    async def delete(self, rule: RecurringExpense) -> None:
        """Stage a hard delete. Not applied until ``UnitOfWork.flush``."""
        ...
