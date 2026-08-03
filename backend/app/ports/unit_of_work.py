"""The UnitOfWork port: repositories plus the transaction boundary.

Four operations, not two. The current codebase is *not* "one commit at the end":
``receipt_service`` commits mid-request on purpose so an audit row survives the
``HTTPException`` that follows, uses ``begin_nested()`` savepoints in three
places, and ``category_service``/``monthly_goal_service`` roll the whole request
back on a duplicate key. All four of those need a name here or the seam would
force a behaviour change it has no mandate for.

Rules:

- **Routers never commit.** ``app.deps.provider.get_uow``'s underlying ``get_db``
  teardown owns the commit, exactly as it does today.
- **Services call** ``flush`` and ``savepoint``; only ``receipt_service`` will
  call ``commit``.
"""

from contextlib import AbstractAsyncContextManager
from typing import Protocol

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


class Savepoint(Protocol):
    """A nested transaction that can be abandoned without losing the outer one."""

    async def rollback(self) -> None:
        """Discard everything written since the savepoint was taken."""
        ...


class UnitOfWork(Protocol):
    """One transaction, and the repositories that write inside it.

    The repository set grows one aggregate at a time — see the migration sequence
    in ``docs/data-layer-ports-design.md`` section 5. Everything not listed here
    is still reached through ``Depends(get_db)``, and that keeps working because
    ``get_uow`` derives from ``get_db``: a half-migrated router can take both and
    they share one session and one transaction.

    The set is complete as of Step 7.5. The only code still reaching for a raw
    session is ``app/routers/dev_auth.py``, which is deliberately raw and
    permanently exempt.
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

    async def flush(self) -> None:
        """Push staged writes, assign primary keys, apply defaults.

        Raises :class:`~app.ports.errors.UniqueViolation` or
        :class:`~app.ports.errors.ForeignKeyViolation` when a constraint rejects
        the write. Does not make anything durable.
        """
        ...

    async def commit(self) -> None:
        """Make everything written so far durable."""
        ...

    async def rollback(self) -> None:
        """Discard the entire transaction, not just the write that failed."""
        ...

    def savepoint(self) -> AbstractAsyncContextManager[Savepoint]:
        """Open a nested transaction, rolled back if the block raises."""
        ...
