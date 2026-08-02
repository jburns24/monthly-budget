"""Fixtures for the pure-unit tier.

Everything under ``tests/unit/`` runs against ``app.adapters.memory``: no
database, no port-forward, no NullPool engine, no per-test transaction. If a test
here needs a connection, it belongs in one of the ``*_service`` /
``*_integration`` / ``*_api`` modules instead.
"""

import uuid
from collections.abc import Iterator
from datetime import date

import pytest

from app.adapters.memory.unit_of_work import MemoryUnitOfWork
from app.models.category import Category
from app.models.expense import Expense
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.invite import Invite
from app.models.monthly_goal import MonthlyGoal
from app.models.receipt import Receipt
from app.models.user import User


@pytest.fixture(autouse=True)
def _dispose_app_engine() -> Iterator[None]:
    """Shadow the root conftest's autouse engine-disposal fixture with a no-op.

    The root fixture drains ``app.database.engine``'s connection pool after every
    test, which these tests never touch. Overriding it by name keeps this tier
    genuinely free of async database plumbing.
    """
    yield


@pytest.fixture
def uow() -> MemoryUnitOfWork:
    """An empty in-memory UnitOfWork."""
    return MemoryUnitOfWork()


@pytest.fixture
def family_id() -> uuid.UUID:
    """A family id to scope test data to. No Family row is needed."""
    return uuid.uuid4()


def make_category(family_id: uuid.UUID, name: str, *, sort_order: int = 0, is_active: bool = True) -> Category:
    """Build an unattached Category. ``id`` and ``created_at`` are left to flush()."""
    return Category(family_id=family_id, name=name, sort_order=sort_order, is_active=is_active)


def make_expense(
    family_id: uuid.UUID,
    category_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
    amount_cents: int = 1000,
    description: str = "unit test expense",
    expense_date: date = date(2026, 4, 1),
    year_month: str = "2026-04",
    receipt_id: uuid.UUID | None = None,
) -> Expense:
    """Build an unattached Expense referencing ``category_id``."""
    return Expense(
        family_id=family_id,
        user_id=user_id or uuid.uuid4(),
        category_id=category_id,
        amount_cents=amount_cents,
        description=description,
        expense_date=expense_date,
        year_month=year_month,
        receipt_id=receipt_id,
    )


def make_receipt(family_id: uuid.UUID, uploaded_by: uuid.UUID, *, status: str = "completed") -> Receipt:
    """Build an unattached Receipt. ``id`` and ``created_at`` are left to flush()."""
    return Receipt(family_id=family_id, uploaded_by=uploaded_by, status=status)


def make_monthly_goal(
    family_id: uuid.UUID,
    category_id: uuid.UUID,
    year_month: str,
    *,
    amount_cents: int = 10000,
    version: int = 1,
) -> MonthlyGoal:
    """Build an unattached MonthlyGoal. ``id`` and ``created_at`` are left to flush()."""
    return MonthlyGoal(
        family_id=family_id,
        category_id=category_id,
        year_month=year_month,
        amount_cents=amount_cents,
        version=version,
    )


def make_user(*, email: str | None = None, google_id: str | None = None, display_name: str = "Test User") -> User:
    """Build an unattached User. ``id`` and ``created_at`` are left to flush()."""
    unique = uuid.uuid4().hex[:8]
    return User(
        google_id=google_id or f"google_{unique}",
        email=email or f"test_{unique}@example.com",
        display_name=display_name,
    )


def make_family(created_by: uuid.UUID, *, name: str = "Test Family") -> Family:
    """Build an unattached Family. ``id`` and ``created_at`` are left to flush()."""
    return Family(name=name, created_by=created_by)


def make_invite(
    family_id: uuid.UUID,
    invited_user_id: uuid.UUID,
    invited_by: uuid.UUID,
    *,
    status: str | None = "pending",
) -> Invite:
    """Build an unattached Invite. ``id`` is left to flush().

    ``status=None`` exercises the column's Python-side ``default='pending'``,
    which the store applies at flush time like Postgres would.
    """
    return Invite(family_id=family_id, invited_user_id=invited_user_id, invited_by=invited_by, status=status)


def make_family_member(
    family_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    role: str = "member",
) -> FamilyMember:
    """Build an unattached FamilyMember. ``id`` is left to flush(); ``joined_at`` has no default."""
    return FamilyMember(family_id=family_id, user_id=user_id, role=role, joined_at=None)


async def seed(uow: MemoryUnitOfWork, *rows: object) -> None:
    """Persist ``rows`` as committed state, the way a fixture row would be.

    Committing matters: a later ``rollback()`` restores to the last commit, so
    anything seeded without one is thrown away by the first duplicate-name test.

    Goes through the store rather than a repository so it works uniformly for
    every model, including ones with no dedicated ``add`` yet (e.g. ``Receipt``,
    still Step 7).
    """
    for row in rows:
        uow.store.add(row)
    await uow.commit()  # commit() flushes first, so defaults and unique checks still apply
