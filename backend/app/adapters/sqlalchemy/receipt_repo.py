"""SQLAlchemy implementation of :class:`~app.ports.repositories.receipt.ReceiptRepository`."""

from datetime import date
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receipt import Receipt


class SqlAlchemyReceiptRepository:
    """Receipt reads and writes against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_in_family(self, receipt_id: UUID, family_id: UUID) -> Receipt | None:
        result = await self._session.execute(
            select(Receipt).where(Receipt.id == receipt_id, Receipt.family_id == family_id)
        )
        return result.scalar_one_or_none()

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
        filters: list[Any] = [Receipt.family_id == family_id]
        if status is not None:
            filters.append(Receipt.status == status)
        if uploaded_by is not None:
            filters.append(Receipt.uploaded_by == uploaded_by)
        if date_from is not None:
            filters.append(Receipt.parsed_date >= date_from)
        if date_to is not None:
            filters.append(Receipt.parsed_date <= date_to)

        result = await self._session.execute(
            select(Receipt).where(*filters).order_by(Receipt.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def get_status(self, receipt_id: UUID) -> str | None:
        return await self._session.scalar(select(Receipt.status).where(Receipt.id == receipt_id))

    def add(self, receipt: Receipt) -> None:
        self._session.add(receipt)

    async def delete(self, receipt: Receipt) -> None:
        await self._session.delete(receipt)

    # ------------------------------------------------------------------
    # Postgres tier
    # ------------------------------------------------------------------

    async def claim_for_retry(self, receipt_id: UUID) -> bool:
        """Conditional UPDATE; True only for the caller that observed rowcount 1.

        The ``WHERE status = 'failed'`` predicate is the lock: Postgres
        serializes concurrent UPDATEs of the same row, and the loser re-evaluates
        the predicate against the winner's committed value, matches nothing, and
        gets rowcount 0.
        """
        # AsyncSession.execute is typed as returning Result, which has no
        # rowcount; a DML statement really returns a CursorResult, and rowcount
        # is the whole point of this call.
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(Receipt)
                .where(Receipt.id == receipt_id, Receipt.status == "failed")
                .values(status="processing", error_message=None)
            ),
        )
        return result.rowcount == 1
