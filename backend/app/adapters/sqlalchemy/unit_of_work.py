"""SQLAlchemy implementation of :class:`~app.ports.unit_of_work.UnitOfWork`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from app.adapters.sqlalchemy.budget_query import SqlAlchemyBudgetQuery
from app.adapters.sqlalchemy.category_repo import SqlAlchemyCategoryRepository
from app.adapters.sqlalchemy.errors import translate_integrity_error
from app.adapters.sqlalchemy.expense_repo import SqlAlchemyExpenseRepository
from app.adapters.sqlalchemy.family_member_repo import SqlAlchemyFamilyMemberRepository
from app.adapters.sqlalchemy.family_repo import SqlAlchemyFamilyRepository
from app.adapters.sqlalchemy.invite_repo import SqlAlchemyInviteRepository
from app.adapters.sqlalchemy.monthly_goal_repo import SqlAlchemyMonthlyGoalRepository
from app.adapters.sqlalchemy.user_repo import SqlAlchemyUserRepository
from app.ports.read_models import BudgetQuery
from app.ports.repositories.category import CategoryRepository
from app.ports.repositories.expense import ExpenseRepository
from app.ports.repositories.family import FamilyRepository
from app.ports.repositories.family_member import FamilyMemberRepository
from app.ports.repositories.invite import InviteRepository
from app.ports.repositories.monthly_goal import MonthlyGoalRepository
from app.ports.repositories.user import UserRepository


class SqlAlchemySavepoint:
    """A SQLAlchemy ``begin_nested()`` transaction behind the Savepoint port."""

    def __init__(self, nested: AsyncSessionTransaction) -> None:
        self._nested = nested

    async def rollback(self) -> None:
        await self._nested.rollback()


class SqlAlchemyUnitOfWork:
    """One ``AsyncSession``, one transaction, and the repositories writing into it.

    ``owns_transaction`` is the whole reason the existing test suite keeps
    working. In production ``get_uow`` builds the UoW over ``get_db``'s session
    and owns the transaction. Under test, ``conftest``'s ``db_session`` fixture
    has already called ``session.begin()`` and rolls back at teardown for
    isolation; a real ``commit()`` inside the request would defeat that. Passing
    ``owns_transaction=False`` downgrades ``commit()`` to ``flush()`` so the
    outer transaction survives.

    Note: the session is expected to be built with ``expire_on_commit=False``
    (``AsyncSessionLocal`` and every test fixture do). That is load-bearing for
    the receipt retry path, which hand-syncs an attribute after committing —
    see ``docs/data-layer-ports-design.md`` risk (e). The UoW deliberately does
    not mutate the caller's session to enforce it.
    """

    categories: CategoryRepository
    expenses: ExpenseRepository
    users: UserRepository
    families: FamilyRepository
    members: FamilyMemberRepository
    invites: InviteRepository
    goals: MonthlyGoalRepository
    budget: BudgetQuery

    def __init__(self, session: AsyncSession, *, owns_transaction: bool = True) -> None:
        self._session = session
        self._owns_transaction = owns_transaction
        self.categories = SqlAlchemyCategoryRepository(session)
        self.expenses = SqlAlchemyExpenseRepository(session)
        self.users = SqlAlchemyUserRepository(session)
        self.families = SqlAlchemyFamilyRepository(session)
        self.members = SqlAlchemyFamilyMemberRepository(session)
        self.invites = SqlAlchemyInviteRepository(session)
        self.goals = SqlAlchemyMonthlyGoalRepository(session)
        self.budget = SqlAlchemyBudgetQuery(session)

    async def flush(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as exc:
            translated = translate_integrity_error(exc)
            if translated is None:
                raise
            raise translated from exc

    async def commit(self) -> None:
        if self._owns_transaction:
            await self._session.commit()
        else:
            await self.flush()

    async def rollback(self) -> None:
        # Deliberately unconditional, including when the UoW does not own the
        # transaction. Services that call this today (duplicate-name handling in
        # category and goal creation) discard the *whole* request, and porting
        # that literally is what keeps this step behaviour-neutral. The correct
        # fix is a savepoint; see design doc risk (f).
        await self._session.rollback()

    @asynccontextmanager
    async def savepoint(self) -> AsyncIterator[SqlAlchemySavepoint]:
        async with self._session.begin_nested() as nested:
            yield SqlAlchemySavepoint(nested)
