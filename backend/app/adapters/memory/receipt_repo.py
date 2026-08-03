"""In-memory implementation of :class:`~app.ports.repositories.receipt.ReceiptRepository`.

No relationship population here, unlike ``MemoryExpenseRepository``:
``ReceiptResponse`` reads columns only, so nothing a router does with a Receipt
crosses risk (a).
"""

from datetime import date
from uuid import UUID

from app.adapters.memory.store import MemoryStore, postgres_tier
from app.models.receipt import Receipt


def _matches(
    receipt: Receipt,
    family_id: UUID,
    status: str | None,
    uploaded_by: UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> bool:
    if receipt.family_id != family_id:
        return False
    if status is not None and receipt.status != status:
        return False
    if uploaded_by is not None and receipt.uploaded_by != uploaded_by:
        return False
    if date_from is not None or date_to is not None:
        # SQL comparisons against NULL are never true, so a parsed_date filter
        # drops unparsed rows in Postgres. Mirror that rather than letting a
        # still-processing receipt through the fake.
        if receipt.parsed_date is None:
            return False
        if date_from is not None and receipt.parsed_date < date_from:
            return False
        if date_to is not None and receipt.parsed_date > date_to:
            return False
    return True


class MemoryReceiptRepository:
    """Receipt reads and writes over a :class:`~app.adapters.memory.store.MemoryStore`."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def get_in_family(self, receipt_id: UUID, family_id: UUID) -> Receipt | None:
        receipt = self._store.get(Receipt, receipt_id)
        if receipt is None or receipt.family_id != family_id:
            return None
        return receipt

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
        matches = [
            r for r in self._store.rows(Receipt) if _matches(r, family_id, status, uploaded_by, date_from, date_to)
        ]
        matches.sort(key=lambda r: r.created_at, reverse=True)
        return matches[offset : offset + limit]

    async def get_status(self, receipt_id: UUID) -> str | None:
        receipt = self._store.get(Receipt, receipt_id)
        return None if receipt is None else receipt.status

    def add(self, receipt: Receipt) -> None:
        self._store.add(receipt)

    async def delete(self, receipt: Receipt) -> None:
        self._store.delete(receipt)

    # ------------------------------------------------------------------
    # Postgres tier
    # ------------------------------------------------------------------

    async def claim_for_retry(self, receipt_id: UUID) -> bool:
        postgres_tier(
            "ReceiptRepository.claim_for_retry",
            "row-lock serialization of a conditional UPDATE, which a single-threaded fake would "
            "trivially satisfy without ever exercising the concurrency it exists to prevent",
        )
