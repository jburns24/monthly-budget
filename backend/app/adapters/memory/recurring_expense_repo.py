"""In-memory implementation of :class:`~app.ports.repositories.recurring_expense.RecurringExpenseRepository`."""

from datetime import date
from uuid import UUID

from app.adapters.memory.store import MemoryStore
from app.models.recurring_expense import RecurringExpense


class MemoryRecurringExpenseRepository:
    """RecurringExpense reads and writes over a :class:`~app.adapters.memory.store.MemoryStore`."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def list_for_family(self, family_id: UUID) -> list[RecurringExpense]:
        rules = [r for r in self._store.rows(RecurringExpense) if r.family_id == family_id]
        return sorted(rules, key=lambda r: r.created_at, reverse=True)

    async def get_in_family(self, rule_id: UUID, family_id: UUID) -> RecurringExpense | None:
        rule = self._store.get(RecurringExpense, rule_id)
        if rule is None or rule.family_id != family_id:
            return None
        return rule

    async def lock_due(self, family_id: UUID, today: date) -> list[RecurringExpense]:
        # Single-transaction store: there is no concurrent writer to lock against.
        due = [
            r
            for r in self._store.rows(RecurringExpense)
            if r.family_id == family_id and r.is_active and r.next_due_date <= today
        ]
        return sorted(due, key=lambda r: r.created_at)

    def add(self, rule: RecurringExpense) -> None:
        self._store.add(rule)

    async def delete(self, rule: RecurringExpense) -> None:
        self._store.delete(rule)
