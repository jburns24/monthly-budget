"""Repository protocol for the Expense aggregate.

``count_by_category`` is the one cross-aggregate read: ``category_service`` uses
it to decide whether deleting a category hard-deletes or archives it. The rest
is the inventory from ``docs/data-layer-ports-design.md`` section 3.

Risk (a): ``ExpenseResponse`` (``app/schemas/expense.py``) has
``from_attributes=True`` and walks ``expense.category``, ``expense.user``, and
``receipt_status`` (an ORM ``@property`` reading ``self.receipt``). Every method
that hands an ``Expense`` to a router MUST populate those three relationships or
``model_validate`` raises ``MissingGreenlet`` against the SQLAlchemy adapter (a
lazy load with no event loop to await it) or silently returns ``None`` /
``AttributeError`` against the in-memory adapter. The two read methods below are
named for exactly what they load: ``get_in_family`` loads nothing extra,
``get_in_family_with_details`` eager-loads category, user, and receipt.
``list_for_month`` always eager-loads, because every expense in a list response
walks the same three relationships.
"""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.models.expense import Expense
from app.ports.read_models import AssetExpenseLink


class ExpenseRepository(Protocol):
    """Reads and writes for :class:`~app.models.expense.Expense`."""

    async def get_in_family(self, expense_id: UUID, family_id: UUID) -> Expense | None:
        """Return the expense if it exists *and* belongs to ``family_id``, else None.

        No relationships are loaded — safe only for code that reads column
        attributes (optimistic-lock checks, field mutation). Reading
        ``.category``, ``.user``, or ``.receipt``/``receipt_status`` off the
        result crosses risk (a); use :meth:`get_in_family_with_details` instead.
        """
        ...

    async def get_in_family_with_details(self, expense_id: UUID, family_id: UUID) -> Expense | None:
        """Return the expense with ``category``, ``user``, and ``receipt`` populated.

        This is what every router-facing read needs, since ``ExpenseResponse``
        walks all three.
        """
        ...

    async def list_for_month(
        self,
        family_id: UUID,
        year_month: str,
        category_id: UUID | None,
        limit: int,
        offset: int,
        entry_type: str | None = None,
    ) -> list[Expense]:
        """Return a page of expenses for ``family_id`` in ``year_month``, newest first.

        Ordered by ``(expense_date DESC, created_at DESC)``. ``category``,
        ``user``, and ``receipt`` are eager-loaded on every row, same as
        :meth:`get_in_family_with_details`. Optionally filtered by
        ``category_id`` and/or ``entry_type`` (``'expense'`` / ``'income'``).
        Income rows may have a null ``category``.
        """
        ...

    async def count_for_month(
        self,
        family_id: UUID,
        year_month: str,
        category_id: UUID | None,
        entry_type: str | None = None,
    ) -> int:
        """Return the total count backing :meth:`list_for_month`'s pagination."""
        ...

    async def count_by_category(self, category_id: UUID) -> int:
        """Return how many expenses reference ``category_id``, across all months."""
        ...

    async def list_for_asset(self, asset_id: UUID, family_id: UUID) -> list[Expense]:
        """Return every expense linked to ``asset_id``, newest first.

        Ordered by ``(expense_date DESC, created_at DESC)`` with ``category``,
        ``user`` and ``receipt`` eager-loaded, same as :meth:`list_for_month`.
        """
        ...

    async def list_asset_links(self, family_id: UUID, asset_ids: Sequence[UUID]) -> list[AssetExpenseLink]:
        """Return the light projection of every expense linked to any of ``asset_ids``.

        One query for any number of assets, no relationships loaded, no particular order.
        """
        ...

    async def clear_asset_link(self, asset_id: UUID) -> None:
        """Set ``asset_id`` and ``asset_role`` to NULL on every expense linked to ``asset_id``.

        Applied immediately in Postgres (a bulk UPDATE); the in-memory adapter
        stages it as ordinary dirty-tracked writes. Called before the asset is
        deleted, because the FK's SET NULL alone would leave the role dangling.
        """
        ...

    def add(self, expense: Expense) -> None:
        """Stage a new expense. Not durable until ``UnitOfWork.flush``."""
        ...

    async def delete(self, expense: Expense) -> None:
        """Stage a hard delete. Not applied until ``UnitOfWork.flush``."""
        ...
