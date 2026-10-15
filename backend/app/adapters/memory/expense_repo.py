"""In-memory implementation of :class:`~app.ports.repositories.expense.ExpenseRepository`.

Risk (a): ``get_in_family_with_details`` and ``list_for_month`` must explicitly
populate ``.category``, ``.user``, and ``.receipt`` on every returned instance.
Under the real ORM those come from ``selectinload``; here there is no session to
lazy-load from, so an unpopulated relationship attribute is just ``None`` —
``ExpenseResponse.model_validate`` would silently accept a ``None`` category
where the schema requires one, or raise a Pydantic validation error, never the
``MissingGreenlet`` a router would see against Postgres. Populating them here is
what makes the fake honestly interchangeable with the SQLAlchemy adapter.
"""

from collections.abc import Sequence
from uuid import UUID

from app.adapters.memory.store import MemoryStore
from app.models.category import Category
from app.models.expense import Expense
from app.models.receipt import Receipt
from app.models.user import User
from app.ports.read_models import AssetExpenseLink


def _matches_month(
    expense: Expense,
    family_id: UUID,
    year_month: str,
    category_id: UUID | None,
    entry_type: str | None = None,
) -> bool:
    return (
        expense.family_id == family_id
        and expense.year_month == year_month
        and (category_id is None or expense.category_id == category_id)
        and (entry_type is None or expense.entry_type == entry_type)
    )


class MemoryExpenseRepository:
    """Expense reads and writes over a :class:`~app.adapters.memory.store.MemoryStore`."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def _attach_details(self, expense: Expense) -> Expense:
        expense.category = self._store.get(Category, expense.category_id) if expense.category_id is not None else None
        expense.user = self._store.get(User, expense.user_id)
        expense.receipt = self._store.get(Receipt, expense.receipt_id) if expense.receipt_id else None
        return expense

    async def get_in_family(self, expense_id: UUID, family_id: UUID) -> Expense | None:
        expense = self._store.get(Expense, expense_id)
        if expense is None or expense.family_id != family_id:
            return None
        return expense

    async def get_in_family_with_details(self, expense_id: UUID, family_id: UUID) -> Expense | None:
        expense = await self.get_in_family(expense_id, family_id)
        if expense is None:
            return None
        return self._attach_details(expense)

    async def list_for_month(
        self,
        family_id: UUID,
        year_month: str,
        category_id: UUID | None,
        limit: int,
        offset: int,
        entry_type: str | None = None,
    ) -> list[Expense]:
        matches = [
            e for e in self._store.rows(Expense) if _matches_month(e, family_id, year_month, category_id, entry_type)
        ]
        matches.sort(key=lambda e: (e.expense_date, e.created_at), reverse=True)
        page = matches[offset : offset + limit]
        return [self._attach_details(e) for e in page]

    async def count_for_month(
        self,
        family_id: UUID,
        year_month: str,
        category_id: UUID | None,
        entry_type: str | None = None,
    ) -> int:
        return sum(
            1 for e in self._store.rows(Expense) if _matches_month(e, family_id, year_month, category_id, entry_type)
        )

    async def count_by_category(self, category_id: UUID) -> int:
        return sum(1 for expense in self._store.rows(Expense) if expense.category_id == category_id)

    async def list_for_asset(self, asset_id: UUID, family_id: UUID) -> list[Expense]:
        linked = [e for e in self._store.rows(Expense) if e.asset_id == asset_id and e.family_id == family_id]
        linked.sort(key=lambda e: (e.expense_date, e.created_at), reverse=True)
        return [self._attach_details(e) for e in linked]

    async def list_asset_links(self, family_id: UUID, asset_ids: Sequence[UUID]) -> list[AssetExpenseLink]:
        wanted = set(asset_ids)
        return [
            AssetExpenseLink(e.asset_id, e.expense_date, e.amount_cents, e.asset_role, e.entry_type)
            for e in self._store.rows(Expense)
            if e.family_id == family_id and e.asset_id in wanted and e.asset_id is not None and e.asset_role is not None
        ]

    async def clear_asset_link(self, asset_id: UUID) -> None:
        for expense in self._store.rows(Expense):
            if expense.asset_id == asset_id:
                expense.asset_id = None
                expense.asset_role = None

    def add(self, expense: Expense) -> None:
        self._store.add(expense)

    async def delete(self, expense: Expense) -> None:
        self._store.delete(expense)
