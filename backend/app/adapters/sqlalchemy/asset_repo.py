"""SQLAlchemy implementations of the asset repositories in :mod:`app.ports.repositories.asset`."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetContribution, AssetLoan, AssetLoanBalanceCorrection, AssetValuation


class SqlAlchemyAssetRepository:
    """Asset reads and writes against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_family(self, family_id: UUID) -> list[Asset]:
        result = await self._session.execute(
            select(Asset)
            .where(Asset.family_id == family_id)
            .order_by(Asset.purchase_date.desc(), Asset.created_at.desc(), Asset.id)
        )
        return list(result.scalars().all())

    async def get_in_family(self, asset_id: UUID, family_id: UUID) -> Asset | None:
        result = await self._session.execute(select(Asset).where(Asset.id == asset_id, Asset.family_id == family_id))
        return result.scalar_one_or_none()

    def add(self, asset: Asset) -> None:
        self._session.add(asset)

    async def delete(self, asset: Asset) -> None:
        await self._session.delete(asset)


class SqlAlchemyAssetLoanRepository:
    """AssetLoan (and balance correction) reads and writes against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_asset(self, asset_id: UUID) -> AssetLoan | None:
        result = await self._session.execute(select(AssetLoan).where(AssetLoan.asset_id == asset_id))
        return result.scalar_one_or_none()

    async def list_for_assets(self, asset_ids: Sequence[UUID]) -> list[AssetLoan]:
        if not asset_ids:
            return []
        result = await self._session.execute(select(AssetLoan).where(AssetLoan.asset_id.in_(asset_ids)))
        return list(result.scalars().all())

    async def list_corrections_for_loans(self, loan_ids: Sequence[UUID]) -> list[AssetLoanBalanceCorrection]:
        if not loan_ids:
            return []
        result = await self._session.execute(
            select(AssetLoanBalanceCorrection)
            .where(AssetLoanBalanceCorrection.loan_id.in_(loan_ids))
            .order_by(AssetLoanBalanceCorrection.as_of_date, AssetLoanBalanceCorrection.id)
        )
        return list(result.scalars().all())

    async def list_corrections(self, loan_id: UUID) -> list[AssetLoanBalanceCorrection]:
        result = await self._session.execute(
            select(AssetLoanBalanceCorrection)
            .where(AssetLoanBalanceCorrection.loan_id == loan_id)
            .order_by(AssetLoanBalanceCorrection.as_of_date, AssetLoanBalanceCorrection.id)
        )
        return list(result.scalars().all())

    async def get_correction_in_loan(self, correction_id: UUID, loan_id: UUID) -> AssetLoanBalanceCorrection | None:
        result = await self._session.execute(
            select(AssetLoanBalanceCorrection).where(
                AssetLoanBalanceCorrection.id == correction_id, AssetLoanBalanceCorrection.loan_id == loan_id
            )
        )
        return result.scalar_one_or_none()

    def add(self, loan: AssetLoan) -> None:
        self._session.add(loan)

    async def delete(self, loan: AssetLoan) -> None:
        await self._session.delete(loan)

    def add_correction(self, correction: AssetLoanBalanceCorrection) -> None:
        self._session.add(correction)

    async def delete_correction(self, correction: AssetLoanBalanceCorrection) -> None:
        await self._session.delete(correction)


class SqlAlchemyAssetValuationRepository:
    """AssetValuation reads and writes against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_asset(self, asset_id: UUID) -> list[AssetValuation]:
        result = await self._session.execute(
            select(AssetValuation)
            .where(AssetValuation.asset_id == asset_id)
            .order_by(AssetValuation.as_of_date, AssetValuation.id)
        )
        return list(result.scalars().all())

    async def list_for_assets(self, asset_ids: Sequence[UUID]) -> list[AssetValuation]:
        if not asset_ids:
            return []
        result = await self._session.execute(
            select(AssetValuation)
            .where(AssetValuation.asset_id.in_(asset_ids))
            .order_by(AssetValuation.as_of_date, AssetValuation.id)
        )
        return list(result.scalars().all())

    async def get_in_asset(self, valuation_id: UUID, asset_id: UUID) -> AssetValuation | None:
        result = await self._session.execute(
            select(AssetValuation).where(AssetValuation.id == valuation_id, AssetValuation.asset_id == asset_id)
        )
        return result.scalar_one_or_none()

    def add(self, valuation: AssetValuation) -> None:
        self._session.add(valuation)

    async def delete(self, valuation: AssetValuation) -> None:
        await self._session.delete(valuation)


class SqlAlchemyAssetContributionRepository:
    """AssetContribution reads and writes against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_asset(self, asset_id: UUID) -> list[AssetContribution]:
        result = await self._session.execute(
            select(AssetContribution)
            .where(AssetContribution.asset_id == asset_id)
            .order_by(AssetContribution.contribution_date, AssetContribution.created_at, AssetContribution.id)
        )
        return list(result.scalars().all())

    async def list_for_assets(self, asset_ids: Sequence[UUID]) -> list[AssetContribution]:
        if not asset_ids:
            return []
        result = await self._session.execute(
            select(AssetContribution)
            .where(AssetContribution.asset_id.in_(asset_ids))
            .order_by(AssetContribution.contribution_date, AssetContribution.created_at, AssetContribution.id)
        )
        return list(result.scalars().all())

    async def get_in_asset(self, contribution_id: UUID, asset_id: UUID) -> AssetContribution | None:
        result = await self._session.execute(
            select(AssetContribution).where(
                AssetContribution.id == contribution_id, AssetContribution.asset_id == asset_id
            )
        )
        return result.scalar_one_or_none()

    def add(self, contribution: AssetContribution) -> None:
        self._session.add(contribution)

    async def delete(self, contribution: AssetContribution) -> None:
        await self._session.delete(contribution)
