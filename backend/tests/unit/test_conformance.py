"""Runtime conformance checks for both persistence adapters. No database.

``app.adapters.conformance`` proves adapter/port conformance *statically*, which
is the design's replacement for the ``NotImplementedError`` safety net an ABC
would give. mypy is not yet wired into CI, though, so these tests assert the same
thing at runtime: every method a port declares exists on every adapter.

They check names and callability only — mypy checks the signatures. Together they
catch the drift that matters: adding a method to a port and forgetting an adapter.
"""

from typing import Any, Protocol

import pytest

import app.adapters.conformance  # noqa: F401 — importing it is the smoke test for the static assertions
from app.adapters.memory.budget_query import MemoryBudgetQuery
from app.adapters.memory.category_repo import MemoryCategoryRepository
from app.adapters.memory.expense_repo import MemoryExpenseRepository
from app.adapters.memory.family_member_repo import MemoryFamilyMemberRepository
from app.adapters.memory.family_repo import MemoryFamilyRepository
from app.adapters.memory.invite_repo import MemoryInviteRepository
from app.adapters.memory.monthly_goal_repo import MemoryMonthlyGoalRepository
from app.adapters.memory.receipt_repo import MemoryReceiptRepository
from app.adapters.memory.refresh_token_repo import MemoryRefreshTokenRepository
from app.adapters.memory.unit_of_work import MemorySavepoint, MemoryUnitOfWork
from app.adapters.memory.user_repo import MemoryUserRepository
from app.adapters.sqlalchemy.budget_query import SqlAlchemyBudgetQuery
from app.adapters.sqlalchemy.category_repo import SqlAlchemyCategoryRepository
from app.adapters.sqlalchemy.expense_repo import SqlAlchemyExpenseRepository
from app.adapters.sqlalchemy.family_member_repo import SqlAlchemyFamilyMemberRepository
from app.adapters.sqlalchemy.family_repo import SqlAlchemyFamilyRepository
from app.adapters.sqlalchemy.invite_repo import SqlAlchemyInviteRepository
from app.adapters.sqlalchemy.monthly_goal_repo import SqlAlchemyMonthlyGoalRepository
from app.adapters.sqlalchemy.receipt_repo import SqlAlchemyReceiptRepository
from app.adapters.sqlalchemy.refresh_token_repo import SqlAlchemyRefreshTokenRepository
from app.adapters.sqlalchemy.unit_of_work import SqlAlchemySavepoint, SqlAlchemyUnitOfWork
from app.adapters.sqlalchemy.user_repo import SqlAlchemyUserRepository
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
from app.ports.unit_of_work import Savepoint, UnitOfWork


def _declared_methods(protocol: type[Protocol]) -> set[str]:  # type: ignore[valid-type]
    """Return the public method names a Protocol declares."""
    return {name for name, value in vars(protocol).items() if not name.startswith("_") and callable(value)}


def _missing(protocol: type[Any], adapter: type[Any]) -> set[str]:
    return {name for name in _declared_methods(protocol) if not callable(getattr(adapter, name, None))}


# Every port, with the two adapters that must satisfy it. One row per aggregate:
# adding a port to the seam should cost a line here, not another test function.
_PORTS_AND_ADAPTERS = [
    (CategoryRepository, SqlAlchemyCategoryRepository, MemoryCategoryRepository),
    (ExpenseRepository, SqlAlchemyExpenseRepository, MemoryExpenseRepository),
    (MonthlyGoalRepository, SqlAlchemyMonthlyGoalRepository, MemoryMonthlyGoalRepository),
    (BudgetQuery, SqlAlchemyBudgetQuery, MemoryBudgetQuery),
    (UserRepository, SqlAlchemyUserRepository, MemoryUserRepository),
    (FamilyRepository, SqlAlchemyFamilyRepository, MemoryFamilyRepository),
    (FamilyMemberRepository, SqlAlchemyFamilyMemberRepository, MemoryFamilyMemberRepository),
    (InviteRepository, SqlAlchemyInviteRepository, MemoryInviteRepository),
    (ReceiptRepository, SqlAlchemyReceiptRepository, MemoryReceiptRepository),
    (RefreshTokenRepository, SqlAlchemyRefreshTokenRepository, MemoryRefreshTokenRepository),
    (UnitOfWork, SqlAlchemyUnitOfWork, MemoryUnitOfWork),
    (Savepoint, SqlAlchemySavepoint, MemorySavepoint),
]


@pytest.mark.parametrize(
    ("port", "sql_adapter", "memory_adapter"),
    _PORTS_AND_ADAPTERS,
    ids=[port.__name__ for port, _, _ in _PORTS_AND_ADAPTERS],
)
def test_ports_are_fully_implemented_by_both_adapters(
    port: type[Any], sql_adapter: type[Any], memory_adapter: type[Any]
) -> None:
    """Every method a port declares exists on both adapters, PG-tier ones included."""
    assert _declared_methods(port)  # guard against a silent empty set
    assert _missing(port, sql_adapter) == set()
    assert _missing(port, memory_adapter) == set()


def test_the_transaction_boundary_is_four_operations_plus_a_savepoint_handle() -> None:
    """Pin the UoW surface itself: the design needs all four, not just commit/rollback."""
    assert _declared_methods(UnitOfWork) == {"flush", "commit", "rollback", "savepoint"}
    assert _declared_methods(Savepoint) == {"rollback"}


def test_unit_of_work_implementations_expose_the_same_repositories() -> None:
    """A service written against one UoW must find the same attributes on the other."""
    declared = set(UnitOfWork.__annotations__)

    assert declared == {
        "categories",
        "expenses",
        "users",
        "families",
        "members",
        "invites",
        "goals",
        "receipts",
        "tokens",
        "budget",
    }
    assert declared <= set(SqlAlchemyUnitOfWork.__annotations__)
    assert declared <= set(MemoryUnitOfWork.__annotations__)
