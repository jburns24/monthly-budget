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

    async def get_status(self, receipt_id: UUID) -> str | None:
        """Return the persisted ``status`` column, or None if the row is gone.

        Reads the column directly rather than an instance attribute: the caller
        (``claim_receipt_for_retry``'s 409 path) needs the *true* persisted value
        precisely because the ORM instance it holds may be stale — another
        session may already have claimed the row.
        """
        ...

    def add(self, receipt: Receipt) -> None:
        """Stage a new receipt. Not durable until ``UnitOfWork.flush``."""
        ...

    async def delete(self, receipt: Receipt) -> None:
        """Stage a hard delete. Not applied until ``UnitOfWork.flush``."""
        ...

    # ------------------------------------------------------------------
    # Postgres tier: no in-memory implementation, integration tests only.
    # ------------------------------------------------------------------

    async def claim_for_retry(self, receipt_id: UUID) -> bool:
        """Move ``receipt_id`` from ``status='failed'`` to ``'processing'``.

        Returns True for the caller that won the row, False for everyone else.

        Postgres tier, and the one method here where that classification is not
        about SQL features but about the *guarantee*. The contract is that two
        concurrent retries cannot both proceed (which would double-charge
        Claude), and it is delivered by a conditional
        ``UPDATE ... WHERE id = ? AND status = 'failed'`` that the database
        serializes at row-lock granularity. A single-threaded in-memory fake
        would return True-then-False and "pass" without ever exercising the
        locking that is the entire point, so it would prove nothing. See
        ``docs/data-layer-ports-design.md`` section 3.
        """
        ...
