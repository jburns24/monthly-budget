"""In-memory implementations of the asset repositories in :mod:`app.ports.repositories.asset`."""

from collections.abc import Sequence
from uuid import UUID

from app.adapters.memory.store import MemoryStore
from app.models.asset import Asset, AssetContribution, AssetLoan, AssetLoanBalanceCorrection, AssetValuation


class MemoryAssetRepository:
    """Asset reads and writes over a :class:`~app.adapters.memory.store.MemoryStore`."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def list_for_family(self, family_id: UUID) -> list[Asset]:
        assets = [a for a in self._store.rows(Asset) if a.family_id == family_id]
        return sorted(assets, key=lambda a: (a.purchase_date, a.created_at), reverse=True)

    async def get_in_family(self, asset_id: UUID, family_id: UUID) -> Asset | None:
        asset = self._store.get(Asset, asset_id)
        if asset is None or asset.family_id != family_id:
            return None
        return asset

    def add(self, asset: Asset) -> None:
        self._store.add(asset)

    async def delete(self, asset: Asset) -> None:
        self._store.delete(asset)


class MemoryAssetLoanRepository:
    """AssetLoan (and balance correction) reads and writes over a MemoryStore."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def get_for_asset(self, asset_id: UUID) -> AssetLoan | None:
        return next((loan for loan in self._store.rows(AssetLoan) if loan.asset_id == asset_id), None)

    async def list_for_assets(self, asset_ids: Sequence[UUID]) -> list[AssetLoan]:
        wanted = set(asset_ids)
        return [loan for loan in self._store.rows(AssetLoan) if loan.asset_id in wanted]

    async def list_corrections_for_loans(self, loan_ids: Sequence[UUID]) -> list[AssetLoanBalanceCorrection]:
        wanted = set(loan_ids)
        corrections = [c for c in self._store.rows(AssetLoanBalanceCorrection) if c.loan_id in wanted]
        return sorted(corrections, key=lambda c: c.as_of_date)

    async def list_corrections(self, loan_id: UUID) -> list[AssetLoanBalanceCorrection]:
        corrections = [c for c in self._store.rows(AssetLoanBalanceCorrection) if c.loan_id == loan_id]
        return sorted(corrections, key=lambda c: c.as_of_date)

    async def get_correction_in_loan(self, correction_id: UUID, loan_id: UUID) -> AssetLoanBalanceCorrection | None:
        correction = self._store.get(AssetLoanBalanceCorrection, correction_id)
        if correction is None or correction.loan_id != loan_id:
            return None
        return correction

    def add(self, loan: AssetLoan) -> None:
        self._store.add(loan)

    async def delete(self, loan: AssetLoan) -> None:
        self._store.delete(loan)

    def add_correction(self, correction: AssetLoanBalanceCorrection) -> None:
        self._store.add(correction)

    async def delete_correction(self, correction: AssetLoanBalanceCorrection) -> None:
        self._store.delete(correction)


class MemoryAssetValuationRepository:
    """AssetValuation reads and writes over a MemoryStore."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def list_for_asset(self, asset_id: UUID) -> list[AssetValuation]:
        valuations = [v for v in self._store.rows(AssetValuation) if v.asset_id == asset_id]
        return sorted(valuations, key=lambda v: v.as_of_date)

    async def list_for_assets(self, asset_ids: Sequence[UUID]) -> list[AssetValuation]:
        wanted = set(asset_ids)
        valuations = [v for v in self._store.rows(AssetValuation) if v.asset_id in wanted]
        return sorted(valuations, key=lambda v: v.as_of_date)

    async def get_in_asset(self, valuation_id: UUID, asset_id: UUID) -> AssetValuation | None:
        valuation = self._store.get(AssetValuation, valuation_id)
        if valuation is None or valuation.asset_id != asset_id:
            return None
        return valuation

    def add(self, valuation: AssetValuation) -> None:
        self._store.add(valuation)

    async def delete(self, valuation: AssetValuation) -> None:
        self._store.delete(valuation)


class MemoryAssetContributionRepository:
    """AssetContribution reads and writes over a MemoryStore."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def list_for_asset(self, asset_id: UUID) -> list[AssetContribution]:
        contributions = [c for c in self._store.rows(AssetContribution) if c.asset_id == asset_id]
        return sorted(contributions, key=lambda c: (c.contribution_date, c.created_at))

    async def list_for_assets(self, asset_ids: Sequence[UUID]) -> list[AssetContribution]:
        wanted = set(asset_ids)
        contributions = [c for c in self._store.rows(AssetContribution) if c.asset_id in wanted]
        return sorted(contributions, key=lambda c: (c.contribution_date, c.created_at))

    async def get_in_asset(self, contribution_id: UUID, asset_id: UUID) -> AssetContribution | None:
        contribution = self._store.get(AssetContribution, contribution_id)
        if contribution is None or contribution.asset_id != asset_id:
            return None
        return contribution

    def add(self, contribution: AssetContribution) -> None:
        self._store.add(contribution)

    async def delete(self, contribution: AssetContribution) -> None:
        self._store.delete(contribution)
