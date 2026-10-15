"""Repository protocols for the Asset aggregate and its children."""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.models.asset import Asset, AssetContribution, AssetLoan, AssetLoanBalanceCorrection, AssetValuation


class AssetRepository(Protocol):
    """Reads and writes for :class:`~app.models.asset.Asset`.

    Deleting an asset cascades to its loan, corrections, valuations and contributions
    in Postgres; the in-memory adapter does not emulate ``ON DELETE CASCADE``.
    """

    async def list_for_family(self, family_id: UUID) -> list[Asset]:
        """Return every asset for ``family_id``, newest purchase first."""
        ...

    async def get_in_family(self, asset_id: UUID, family_id: UUID) -> Asset | None:
        """Return the asset if it exists *and* belongs to ``family_id``, else None."""
        ...

    def add(self, asset: Asset) -> None:
        """Stage a new asset. Not durable until ``UnitOfWork.flush``."""
        ...

    async def delete(self, asset: Asset) -> None:
        """Stage a hard delete. Not applied until ``UnitOfWork.flush``."""
        ...


class AssetLoanRepository(Protocol):
    """Reads and writes for :class:`~app.models.asset.AssetLoan` and its balance corrections.

    Callers must have proved the asset belongs to the family first; nothing here
    takes a ``family_id``.
    """

    async def get_for_asset(self, asset_id: UUID) -> AssetLoan | None:
        """Return the asset's loan, or None if it has none."""
        ...

    async def list_for_assets(self, asset_ids: Sequence[UUID]) -> list[AssetLoan]:
        """Return the loans of any of ``asset_ids`` in one query."""
        ...

    async def list_corrections_for_loans(self, loan_ids: Sequence[UUID]) -> list[AssetLoanBalanceCorrection]:
        """Return the corrections of any of ``loan_ids`` in one query, oldest ``as_of_date`` first."""
        ...

    async def list_corrections(self, loan_id: UUID) -> list[AssetLoanBalanceCorrection]:
        """Return the loan's balance corrections, oldest ``as_of_date`` first."""
        ...

    async def get_correction_in_loan(self, correction_id: UUID, loan_id: UUID) -> AssetLoanBalanceCorrection | None:
        """Return the correction if it exists *and* belongs to ``loan_id``, else None."""
        ...

    def add(self, loan: AssetLoan) -> None:
        """Stage a new loan. Not durable until ``UnitOfWork.flush``."""
        ...

    async def delete(self, loan: AssetLoan) -> None:
        """Stage a loan delete (its corrections are removed by the DB cascade)."""
        ...

    def add_correction(self, correction: AssetLoanBalanceCorrection) -> None:
        """Stage a new balance correction."""
        ...

    async def delete_correction(self, correction: AssetLoanBalanceCorrection) -> None:
        """Stage a correction delete."""
        ...


class AssetValuationRepository(Protocol):
    """Reads and writes for :class:`~app.models.asset.AssetValuation` (manual valuations)."""

    async def list_for_asset(self, asset_id: UUID) -> list[AssetValuation]:
        """Return the asset's manual valuations, oldest ``as_of_date`` first."""
        ...

    async def list_for_assets(self, asset_ids: Sequence[UUID]) -> list[AssetValuation]:
        """Return the manual valuations of any of ``asset_ids`` in one query, oldest ``as_of_date`` first."""
        ...

    async def get_in_asset(self, valuation_id: UUID, asset_id: UUID) -> AssetValuation | None:
        """Return the valuation if it exists *and* belongs to ``asset_id``, else None."""
        ...

    def add(self, valuation: AssetValuation) -> None:
        """Stage a new valuation. Not durable until ``UnitOfWork.flush``."""
        ...

    async def delete(self, valuation: AssetValuation) -> None:
        """Stage a hard delete."""
        ...


class AssetContributionRepository(Protocol):
    """Reads and writes for :class:`~app.models.asset.AssetContribution` (historical contributions)."""

    async def list_for_asset(self, asset_id: UUID) -> list[AssetContribution]:
        """Return the asset's contributions, oldest ``contribution_date`` first."""
        ...

    async def list_for_assets(self, asset_ids: Sequence[UUID]) -> list[AssetContribution]:
        """Return the contributions of any of ``asset_ids`` in one query, oldest ``contribution_date`` first."""
        ...

    async def get_in_asset(self, contribution_id: UUID, asset_id: UUID) -> AssetContribution | None:
        """Return the contribution if it exists *and* belongs to ``asset_id``, else None."""
        ...

    def add(self, contribution: AssetContribution) -> None:
        """Stage a new contribution. Not durable until ``UnitOfWork.flush``."""
        ...

    async def delete(self, contribution: AssetContribution) -> None:
        """Stage a hard delete."""
        ...
