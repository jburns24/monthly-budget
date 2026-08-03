"""In-memory implementation of :class:`~app.ports.unit_of_work.UnitOfWork`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.adapters.memory.budget_query import MemoryBudgetQuery
from app.adapters.memory.category_repo import MemoryCategoryRepository
from app.adapters.memory.expense_repo import MemoryExpenseRepository
from app.adapters.memory.family_member_repo import MemoryFamilyMemberRepository
from app.adapters.memory.family_repo import MemoryFamilyRepository
from app.adapters.memory.invite_repo import MemoryInviteRepository
from app.adapters.memory.monthly_goal_repo import MemoryMonthlyGoalRepository
from app.adapters.memory.receipt_repo import MemoryReceiptRepository
from app.adapters.memory.refresh_token_repo import MemoryRefreshTokenRepository
from app.adapters.memory.store import MemoryStore
from app.adapters.memory.user_repo import MemoryUserRepository
from app.ports.read_models import BudgetQuery
from app.ports.repositories.category import CategoryRepository
from app.ports.repositories.expense import ExpenseRepository
from app.ports.repositories.family import FamilyRepository
from app.ports.repositories.family_member import FamilyMemberRepository
from app.ports.repositories.invite import InviteRepository
from app.ports.repositories.monthly_goal import MonthlyGoalRepository
from app.ports.repositories.receipt import ReceiptRepository
from app.ports.repositories.refresh_token import RefreshTokenRepository
from app.ports.repositories.user import UserRepository


class MemorySavepoint:
    """A snapshot on the store's savepoint stack, addressed by depth."""

    def __init__(self, store: MemoryStore, depth: int) -> None:
        self._store = store
        self._depth = depth

    async def rollback(self) -> None:
        self._store.rollback_to_savepoint(self._depth)


class MemoryUnitOfWork:
    """UnitOfWork over a :class:`~app.adapters.memory.store.MemoryStore`.

    ``commit()`` really commits — there is no ``owns_transaction`` distinction,
    because there is no outer transaction to protect. Tests that need seeded data
    to survive a rollback have to commit it, exactly as the real thing would
    require.

    ``store`` is public so tests can seed rows for aggregates whose repository is
    not ported yet.
    """

    categories: CategoryRepository
    expenses: ExpenseRepository
    users: UserRepository
    families: FamilyRepository
    members: FamilyMemberRepository
    invites: InviteRepository
    goals: MonthlyGoalRepository
    receipts: ReceiptRepository
    tokens: RefreshTokenRepository
    budget: BudgetQuery

    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store if store is not None else MemoryStore()
        self.categories = MemoryCategoryRepository(self.store)
        self.expenses = MemoryExpenseRepository(self.store)
        self.users = MemoryUserRepository(self.store)
        self.families = MemoryFamilyRepository(self.store)
        self.members = MemoryFamilyMemberRepository(self.store)
        self.invites = MemoryInviteRepository(self.store)
        self.goals = MemoryMonthlyGoalRepository(self.store)
        self.receipts = MemoryReceiptRepository(self.store)
        self.tokens = MemoryRefreshTokenRepository(self.store)
        self.budget = MemoryBudgetQuery(self.store)

    async def flush(self) -> None:
        self.store.flush()

    async def commit(self) -> None:
        self.store.commit()

    async def rollback(self) -> None:
        self.store.rollback()

    @asynccontextmanager
    async def savepoint(self) -> AsyncIterator[MemorySavepoint]:
        depth = self.store.push_savepoint()
        try:
            yield MemorySavepoint(self.store, depth)
        except BaseException:
            self.store.rollback_to_savepoint(depth)
            raise
        else:
            self.store.release_savepoint(depth)
