"""Asset service: assets, their loan, balance corrections, manual valuations and contributions.

Every function takes the ``family_id`` the caller proved membership of and resolves the asset
through ``uow.assets.get_in_family``, so another family's asset is a 404, never a 403.

The computed parts of an asset (loan balance, market value, equity, cash in) are not stored; they
are derived from these rows by the pure math in ``app.services.assets``.
"""

import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.logging import get_logger
from app.models.asset import Asset, AssetContribution, AssetLoan, AssetLoanBalanceCorrection, AssetValuation
from app.models.expense import Expense
from app.ports.errors import UniqueViolation
from app.ports.unit_of_work import UnitOfWork

logger = get_logger(__name__)


@dataclass(frozen=True)
class AssetDetailData:
    """An asset with everything stored about it."""

    asset: Asset
    loan: AssetLoan | None
    corrections: list[AssetLoanBalanceCorrection]
    valuations: list[AssetValuation]
    contributions: list[AssetContribution]


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _check_house_location(asset_type: str, state: str | None, zip_code: str | None) -> None:
    if asset_type == "house" and (not state or not zip_code):
        raise _unprocessable("A house requires state and zip_code")


async def _insert_or_conflict(uow: UnitOfWork, stage: Callable[[], None], detail: str) -> None:
    """Stage and flush an insert, turning a unique-key rejection into HTTP 409.

    The insert is staged *inside* the savepoint (opening one flushes what is already pending),
    so only the rejected row is rolled back and the rest of the request survives.
    """
    try:
        async with uow.savepoint():
            stage()
            await uow.flush()
    except UniqueViolation:
        raise HTTPException(status_code=409, detail=detail)


async def get_asset(uow: UnitOfWork, family_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
    """Return the asset, or raise HTTPException(404) if it is missing or in another family."""
    asset = await uow.assets.get_in_family(asset_id, family_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


async def list_assets(uow: UnitOfWork, family_id: uuid.UUID) -> list[Asset]:
    return await uow.assets.list_for_family(family_id)


async def load_details(uow: UnitOfWork, assets: Sequence[Asset]) -> list[AssetDetailData]:
    """Gather each asset's loan, corrections, valuations and contributions in a fixed number of queries.

    The result is in the order of ``assets``, however many there are.
    """
    ids = [a.id for a in assets]
    loans = {loan.asset_id: loan for loan in await uow.asset_loans.list_for_assets(ids)}
    corrections: dict[uuid.UUID, list[AssetLoanBalanceCorrection]] = defaultdict(list)
    for correction in await uow.asset_loans.list_corrections_for_loans([loan.id for loan in loans.values()]):
        corrections[correction.loan_id].append(correction)
    valuations: dict[uuid.UUID, list[AssetValuation]] = defaultdict(list)
    for valuation in await uow.asset_valuations.list_for_assets(ids):
        valuations[valuation.asset_id].append(valuation)
    contributions: dict[uuid.UUID, list[AssetContribution]] = defaultdict(list)
    for contribution in await uow.asset_contributions.list_for_assets(ids):
        contributions[contribution.asset_id].append(contribution)
    return [
        AssetDetailData(
            asset=asset,
            loan=loans.get(asset.id),
            corrections=corrections[loans[asset.id].id] if asset.id in loans else [],
            valuations=valuations[asset.id],
            contributions=contributions[asset.id],
        )
        for asset in assets
    ]


async def load_detail(uow: UnitOfWork, asset: Asset) -> AssetDetailData:
    """Gather one asset's loan, corrections, valuations and contributions."""
    return (await load_details(uow, [asset]))[0]


async def create_asset(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    fields: dict[str, Any],
    loan: dict[str, Any] | None,
) -> Asset:
    """Create an asset, and its loan when ``loan`` terms are given.

    Raises HTTPException(422) for a house without state and zip.
    """
    _check_house_location(fields["asset_type"], fields.get("state"), fields.get("zip_code"))
    now = _now()
    asset = Asset(family_id=family_id, created_by_user_id=user_id, created_at=now, updated_at=now, **fields)
    uow.assets.add(asset)
    await uow.flush()
    if loan is not None:
        uow.asset_loans.add(AssetLoan(asset_id=asset.id, created_at=now, updated_at=now, **loan))
        await uow.flush()
    logger.info(
        "asset_created",
        asset_id=str(asset.id),
        family_id=str(family_id),
        asset_type=asset.asset_type,
        has_loan=loan is not None,
    )
    return asset


async def update_asset(uow: UnitOfWork, family_id: uuid.UUID, asset_id: uuid.UUID, *, fields: dict[str, Any]) -> Asset:
    """Apply the fields present in ``fields`` (so a nullable one can be cleared with ``None``).

    Raises HTTPException(422) if the result is a house without state and zip, or a purchase
    date after the sale date.
    """
    asset = await get_asset(uow, family_id, asset_id)
    for name, value in fields.items():
        setattr(asset, name, value)
    _check_house_location(asset.asset_type, asset.state, asset.zip_code)
    if asset.sold_date is not None and asset.purchase_date > asset.sold_date:
        raise _unprocessable("purchase_date must not be after the sale date")
    asset.updated_at = _now()
    await uow.flush()
    logger.info("asset_updated", asset_id=str(asset_id), family_id=str(family_id), fields=list(fields))
    return asset


async def delete_asset(uow: UnitOfWork, family_id: uuid.UUID, asset_id: uuid.UUID) -> None:
    """Delete an asset. Expenses and recurring rules linked to it stay, unlinked.

    The link and its role are cleared first, in the same transaction: the foreign key's SET NULL
    alone would leave a role without an asset. The loan, corrections, valuations and
    contributions go with the asset through ``ON DELETE CASCADE``.
    """
    asset = await get_asset(uow, family_id, asset_id)
    await uow.expenses.clear_asset_link(asset.id)
    await uow.recurring.clear_asset_link(asset.id)
    await uow.assets.delete(asset)
    await uow.flush()
    logger.info("asset_deleted", asset_id=str(asset_id), family_id=str(family_id))


async def sell_asset(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    *,
    sold_date: date,
    sale_price_cents: int,
    selling_costs_cents: int,
    today: date,
) -> Asset:
    """Mark the asset sold. Raises 409 if it already is, 422 if sold before it was bought or after ``today``.

    ``today`` is the family-local date; a sale cannot be recorded for the future because every
    figure is frozen as of the sale date.
    """
    asset = await get_asset(uow, family_id, asset_id)
    if asset.sold_date is not None:
        raise HTTPException(status_code=409, detail="Asset is already sold")
    if sold_date < asset.purchase_date:
        raise _unprocessable("sold_date must not be before the purchase date")
    if sold_date > today:
        raise _unprocessable("sold_date must not be in the future")
    asset.sold_date = sold_date
    asset.sale_price_cents = sale_price_cents
    asset.selling_costs_cents = selling_costs_cents
    asset.updated_at = _now()
    await uow.flush()
    logger.info("asset_sold", asset_id=str(asset_id), family_id=str(family_id), sold_date=sold_date.isoformat())
    return asset


async def unsell_asset(uow: UnitOfWork, family_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
    """Clear the sale fields. Raises 409 if the asset is not sold."""
    asset = await get_asset(uow, family_id, asset_id)
    if asset.sold_date is None:
        raise HTTPException(status_code=409, detail="Asset is not sold")
    asset.sold_date = None
    asset.sale_price_cents = None
    asset.selling_costs_cents = None
    asset.updated_at = _now()
    await uow.flush()
    logger.info("asset_unsold", asset_id=str(asset_id), family_id=str(family_id))
    return asset


# ---------------------------------------------------------------------------
# Loan and balance corrections
# ---------------------------------------------------------------------------


async def _get_loan(uow: UnitOfWork, asset_id: uuid.UUID) -> AssetLoan:
    loan = await uow.asset_loans.get_for_asset(asset_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


async def upsert_loan(
    uow: UnitOfWork, family_id: uuid.UUID, asset_id: uuid.UUID, *, fields: dict[str, Any]
) -> AssetLoan:
    """Create the asset's loan, or replace its terms (a refinance is new terms plus a correction)."""
    asset = await get_asset(uow, family_id, asset_id)
    now = _now()
    loan = await uow.asset_loans.get_for_asset(asset.id)
    if loan is None:
        loan = AssetLoan(asset_id=asset.id, created_at=now, updated_at=now, **fields)
        uow.asset_loans.add(loan)
    else:
        for name, value in fields.items():
            setattr(loan, name, value)
        loan.updated_at = now
    await uow.flush()
    logger.info("asset_loan_saved", asset_id=str(asset_id), loan_id=str(loan.id), family_id=str(family_id))
    return loan


async def delete_loan(uow: UnitOfWork, family_id: uuid.UUID, asset_id: uuid.UUID) -> None:
    """Delete the asset's loan; its balance corrections go with it (``ON DELETE CASCADE``)."""
    asset = await get_asset(uow, family_id, asset_id)
    loan = await _get_loan(uow, asset.id)
    await uow.asset_loans.delete(loan)
    await uow.flush()
    logger.info("asset_loan_deleted", asset_id=str(asset_id), family_id=str(family_id))


async def add_correction(
    uow: UnitOfWork, family_id: uuid.UUID, asset_id: uuid.UUID, *, as_of_date: date, balance_cents: int
) -> AssetLoanBalanceCorrection:
    """Record the loan's real balance on a date. Raises 404 without a loan, 409 for a repeated date."""
    asset = await get_asset(uow, family_id, asset_id)
    loan = await _get_loan(uow, asset.id)
    correction = AssetLoanBalanceCorrection(
        loan_id=loan.id, as_of_date=as_of_date, balance_cents=balance_cents, created_at=_now()
    )
    await _insert_or_conflict(
        uow, lambda: uow.asset_loans.add_correction(correction), "A balance correction already exists for that date"
    )
    logger.info("asset_loan_correction_added", asset_id=str(asset_id), correction_id=str(correction.id))
    return correction


async def delete_correction(
    uow: UnitOfWork, family_id: uuid.UUID, asset_id: uuid.UUID, correction_id: uuid.UUID
) -> None:
    asset = await get_asset(uow, family_id, asset_id)
    loan = await _get_loan(uow, asset.id)
    correction = await uow.asset_loans.get_correction_in_loan(correction_id, loan.id)
    if correction is None:
        raise HTTPException(status_code=404, detail="Correction not found")
    await uow.asset_loans.delete_correction(correction)
    await uow.flush()
    logger.info("asset_loan_correction_deleted", asset_id=str(asset_id), correction_id=str(correction_id))


# ---------------------------------------------------------------------------
# Manual valuations
# ---------------------------------------------------------------------------


async def add_valuation(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    *,
    as_of_date: date,
    value_cents: int,
    note: str | None,
) -> AssetValuation:
    """Record a manual market value. Raises 409 if there is already one for that date."""
    asset = await get_asset(uow, family_id, asset_id)
    valuation = AssetValuation(
        asset_id=asset.id, as_of_date=as_of_date, value_cents=value_cents, note=note, created_at=_now()
    )
    await _insert_or_conflict(
        uow, lambda: uow.asset_valuations.add(valuation), "A valuation already exists for that date"
    )
    logger.info("asset_valuation_added", asset_id=str(asset_id), valuation_id=str(valuation.id))
    return valuation


async def delete_valuation(uow: UnitOfWork, family_id: uuid.UUID, asset_id: uuid.UUID, valuation_id: uuid.UUID) -> None:
    asset = await get_asset(uow, family_id, asset_id)
    valuation = await uow.asset_valuations.get_in_asset(valuation_id, asset.id)
    if valuation is None:
        raise HTTPException(status_code=404, detail="Valuation not found")
    await uow.asset_valuations.delete(valuation)
    await uow.flush()
    logger.info("asset_valuation_deleted", asset_id=str(asset_id), valuation_id=str(valuation_id))


# ---------------------------------------------------------------------------
# Historical contributions
# ---------------------------------------------------------------------------


async def add_contribution(
    uow: UnitOfWork, family_id: uuid.UUID, asset_id: uuid.UUID, *, fields: dict[str, Any]
) -> AssetContribution:
    asset = await get_asset(uow, family_id, asset_id)
    contribution = AssetContribution(asset_id=asset.id, created_at=_now(), **fields)
    uow.asset_contributions.add(contribution)
    await uow.flush()
    logger.info("asset_contribution_added", asset_id=str(asset_id), contribution_id=str(contribution.id))
    return contribution


async def _get_contribution(
    uow: UnitOfWork, family_id: uuid.UUID, asset_id: uuid.UUID, contribution_id: uuid.UUID
) -> AssetContribution:
    asset = await get_asset(uow, family_id, asset_id)
    contribution = await uow.asset_contributions.get_in_asset(contribution_id, asset.id)
    if contribution is None:
        raise HTTPException(status_code=404, detail="Contribution not found")
    return contribution


async def update_contribution(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    contribution_id: uuid.UUID,
    *,
    fields: dict[str, Any],
) -> AssetContribution:
    contribution = await _get_contribution(uow, family_id, asset_id, contribution_id)
    for name, value in fields.items():
        setattr(contribution, name, value)
    await uow.flush()
    logger.info("asset_contribution_updated", asset_id=str(asset_id), contribution_id=str(contribution_id))
    return contribution


async def delete_contribution(
    uow: UnitOfWork, family_id: uuid.UUID, asset_id: uuid.UUID, contribution_id: uuid.UUID
) -> None:
    contribution = await _get_contribution(uow, family_id, asset_id, contribution_id)
    await uow.asset_contributions.delete(contribution)
    await uow.flush()
    logger.info("asset_contribution_deleted", asset_id=str(asset_id), contribution_id=str(contribution_id))


# ---------------------------------------------------------------------------
# Linked expenses
# ---------------------------------------------------------------------------


async def list_linked_expenses(uow: UnitOfWork, family_id: uuid.UUID, asset_id: uuid.UUID) -> list[Expense]:
    """Expenses linked to the asset, newest first, with category/user/receipt loaded."""
    asset = await get_asset(uow, family_id, asset_id)
    return await uow.expenses.list_for_asset(asset.id, family_id)
