"""Repository protocol for the Receipt aggregate."""

from datetime import date
from typing import Protocol
from uuid import UUID

from app.models.receipt import Receipt


class ReceiptRepository(Protocol):
    """Reads and writes for :class:`~app.models.receipt.Receipt`.

    ``typing.Protocol``, not an ABC: structural typing keeps the in-memory
    adapter from importing the SQLAlchemy one, and lets a service narrow to just
    the methods it uses. Conformance is checked statically by
    ``app.adapters.conformance`` (and, because mypy is not yet wired into CI,
    also at runtime by ``tests/unit/test_conformance.py``).

    Risk (a) does not bite here. ``ReceiptResponse`` is column-only — it never
    walks ``.family``, ``.uploader`` or ``.expense`` — so no method below needs
    an eager-loading variant, unlike ``ExpenseRepository``.
    """

    async def get_in_family(self, receipt_id: UUID, family_id: UUID) -> Receipt | None:
        """Return the receipt if it exists *and* belongs to ``family_id``, else None."""
        ...

    async def list_filtered(
        self,
        family_id: UUID,
        status: str | None,
        uploaded_by: UUID | None,
        date_from: date | None,
        date_to: date | None,
        limit: int,
        offset: int,
    ) -> list[Receipt]:
        """Return a page of the family's receipts, newest ``created_at`` first.

        Each filter is skipped when None. ``date_from``/``date_to`` bound
        ``parsed_date``, which is NULL until Phase 3 succeeds — so a date filter
        also excludes every still-processing and failed receipt, matching the
        inline query this replaced.
        """
        ...

    def add(self, receipt: Receipt) -> None:
        """Stage a new receipt. Not durable until ``UnitOfWork.flush``."""
        ...

    async def delete(self, receipt: Receipt) -> None:
        """Stage a hard delete. Not applied until ``UnitOfWork.flush``."""
        ...
