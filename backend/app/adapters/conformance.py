"""Static conformance assertions for every adapter.

``typing.Protocol`` gives structural typing — the adapters never import the ports
they satisfy — but it also removes the ``NotImplementedError`` safety net an ABC
would provide. This module buys that back at type-check time: each assignment
below fails under mypy if an adapter drifts from its port, including a wrong
parameter name, an ``async def`` that should be ``def``, or a changed return type.

Do not add ``@runtime_checkable`` to the ports instead. It compares method
*names* only, so it would happily accept an adapter whose signatures are wrong.

The module is import-safe and does nothing at runtime: ``cast(Any, None)`` stands
in for the session and store the adapters would otherwise require, and no method
is called. It is imported by ``tests/unit/test_conformance.py``, which re-checks
the same relationships at runtime because mypy is not yet part of CI.
"""

from typing import Any, cast

from app.adapters.memory.budget_query import MemoryBudgetQuery
from app.adapters.memory.category_repo import MemoryCategoryRepository
from app.adapters.memory.expense_repo import MemoryExpenseRepository
from app.adapters.memory.family_member_repo import MemoryFamilyMemberRepository
from app.adapters.memory.family_repo import MemoryFamilyRepository
from app.adapters.memory.invite_repo import MemoryInviteRepository
from app.adapters.memory.monthly_goal_repo import MemoryMonthlyGoalRepository
from app.adapters.memory.store import MemoryStore
from app.adapters.memory.unit_of_work import MemorySavepoint, MemoryUnitOfWork
from app.adapters.memory.user_repo import MemoryUserRepository
from app.adapters.sqlalchemy.budget_query import SqlAlchemyBudgetQuery
from app.adapters.sqlalchemy.category_repo import SqlAlchemyCategoryRepository
from app.adapters.sqlalchemy.expense_repo import SqlAlchemyExpenseRepository
from app.adapters.sqlalchemy.family_member_repo import SqlAlchemyFamilyMemberRepository
from app.adapters.sqlalchemy.family_repo import SqlAlchemyFamilyRepository
from app.adapters.sqlalchemy.invite_repo import SqlAlchemyInviteRepository
from app.adapters.sqlalchemy.monthly_goal_repo import SqlAlchemyMonthlyGoalRepository
from app.adapters.sqlalchemy.unit_of_work import SqlAlchemySavepoint, SqlAlchemyUnitOfWork
from app.adapters.sqlalchemy.user_repo import SqlAlchemyUserRepository
from app.ports.read_models import BudgetQuery
from app.ports.repositories.category import CategoryRepository
from app.ports.repositories.expense import ExpenseRepository
from app.ports.repositories.family import FamilyRepository
from app.ports.repositories.family_member import FamilyMemberRepository
from app.ports.repositories.invite import InviteRepository
from app.ports.repositories.monthly_goal import MonthlyGoalRepository
from app.ports.repositories.user import UserRepository
from app.ports.unit_of_work import Savepoint, UnitOfWork

_NO_SESSION = cast(Any, None)
_NO_STORE = cast(MemoryStore, None)

# --- SQLAlchemy adapter ----------------------------------------------------

_sql_categories: CategoryRepository = SqlAlchemyCategoryRepository(_NO_SESSION)
_sql_expenses: ExpenseRepository = SqlAlchemyExpenseRepository(_NO_SESSION)
_sql_users: UserRepository = SqlAlchemyUserRepository(_NO_SESSION)
_sql_families: FamilyRepository = SqlAlchemyFamilyRepository(_NO_SESSION)
_sql_members: FamilyMemberRepository = SqlAlchemyFamilyMemberRepository(_NO_SESSION)
_sql_invites: InviteRepository = SqlAlchemyInviteRepository(_NO_SESSION)
_sql_goals: MonthlyGoalRepository = SqlAlchemyMonthlyGoalRepository(_NO_SESSION)
_sql_budget: BudgetQuery = SqlAlchemyBudgetQuery(_NO_SESSION)
_sql_savepoint: Savepoint = SqlAlchemySavepoint(_NO_SESSION)
_sql_uow: UnitOfWork = SqlAlchemyUnitOfWork(_NO_SESSION)

# --- In-memory adapter -----------------------------------------------------

_memory_categories: CategoryRepository = MemoryCategoryRepository(_NO_STORE)
_memory_expenses: ExpenseRepository = MemoryExpenseRepository(_NO_STORE)
_memory_users: UserRepository = MemoryUserRepository(_NO_STORE)
_memory_families: FamilyRepository = MemoryFamilyRepository(_NO_STORE)
_memory_members: FamilyMemberRepository = MemoryFamilyMemberRepository(_NO_STORE)
_memory_invites: InviteRepository = MemoryInviteRepository(_NO_STORE)
_memory_goals: MonthlyGoalRepository = MemoryMonthlyGoalRepository(_NO_STORE)
_memory_budget: BudgetQuery = MemoryBudgetQuery(_NO_STORE)
_memory_savepoint: Savepoint = MemorySavepoint(_NO_STORE, 1)
_memory_uow: UnitOfWork = MemoryUnitOfWork(_NO_STORE)
