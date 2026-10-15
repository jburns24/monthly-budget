"""Assets router: houses, vehicles and other things the family owns.

Any member can read assets and link expenses to them; creating, editing, selling, deleting and
maintaining the loan, valuations and contributions is admin-only.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.dependencies import require_family_admin, require_family_member
from app.deps.hpi import get_hpi_refresher
from app.deps.provider import get_uow
from app.models.asset import Asset
from app.models.family_member import FamilyMember
from app.models.user import User
from app.ports.read_models import AssetExpenseLink
from app.ports.unit_of_work import UnitOfWork
from app.schemas.asset import (
    AssetContributionCreate,
    AssetContributionResponse,
    AssetContributionUpdate,
    AssetCreate,
    AssetDetail,
    AssetDetailSummary,
    AssetExpensesResponse,
    AssetHistoryPoint,
    AssetHistoryResponse,
    AssetListItem,
    AssetListResponse,
    AssetListSummary,
    AssetLoanInput,
    AssetLoanResponse,
    AssetResponse,
    AssetSellRequest,
    AssetUpdate,
    AssetValuationCreate,
    AssetValuationInfo,
    AssetValuationResponse,
    HpiRefreshStatusResponse,
    HpiStatusResponse,
    LoanCorrectionCreate,
    LoanCorrectionResponse,
)
from app.schemas.expense import ExpenseResponse
from app.services import asset_analytics, asset_service, hpi_service
from app.services.asset_service import AssetDetailData
from app.services.assets.summary import AssetSummary

router = APIRouter(prefix="/api", tags=["assets"])

AssetMembership = tuple[User, FamilyMember]


def _list_summary(summary: AssetSummary) -> AssetListSummary:
    return AssetListSummary(
        market_value_cents=summary.market_value_cents,
        loan_balance_cents=summary.loan_balance_cents,
        equity_cents=summary.equity_cents,
        cash_in_cents=summary.cash_in_cents,
        valuation_source=summary.valuation_source,
    )


def _detail_summary(summary: AssetSummary) -> AssetDetailSummary:
    buckets = summary.buckets
    return AssetDetailSummary(
        **_list_summary(summary).model_dump(),
        down_payment_cents=buckets.down_payment_cents,
        principal_paid_cents=buckets.principal_paid_cents,
        improvements_cents=buckets.improvements_cents,
        interest_paid_cents=buckets.interest_paid_cents,
        escrow_paid_cents=buckets.escrow_paid_cents,
        closing_costs_cents=buckets.closing_costs_cents,
        maintenance_cents=buckets.maintenance_cents,
        carrying_cost_cents=buckets.carrying_cost_cents,
        equity_building_cents=summary.equity_building_cents,
        sunk_cost_cents=summary.sunk_cost_cents,
        net_gain_cents=summary.net_gain_cents,
    )


def _loan_response(data: AssetDetailData, today: date) -> AssetLoanResponse | None:
    if data.loan is None:
        return None
    payment, payoff = asset_analytics.loan_projection(data.loan, data.corrections, today)
    return AssetLoanResponse.model_validate(data.loan).model_copy(
        update={"computed_monthly_payment_cents": payment, "payoff_date_estimate": payoff}
    )


async def _detail(uow: UnitOfWork, family_id: uuid.UUID, asset_id: uuid.UUID) -> AssetDetail:
    return await _detail_of(uow, family_id, await asset_service.get_asset(uow, family_id, asset_id))


async def _detail_of(uow: UnitOfWork, family_id: uuid.UUID, asset: Asset) -> AssetDetail:
    data = await asset_service.load_detail(uow, asset)
    today = await asset_analytics.today_for_family(uow, family_id)
    index = await asset_analytics.load_index(uow, [asset])
    links = await uow.expenses.list_asset_links(family_id, [asset.id])
    summary = asset_analytics.summarize(data, links, index, today)
    status_row = await uow.hpi.get_status()
    return AssetDetail(
        **AssetResponse.model_validate(asset).model_dump(),
        loan=_loan_response(data, today),
        corrections=[LoanCorrectionResponse.model_validate(c) for c in data.corrections],
        valuations=[AssetValuationResponse.model_validate(v) for v in data.valuations],
        contributions=[AssetContributionResponse.model_validate(c) for c in data.contributions],
        summary=_detail_summary(summary),
        valuation=AssetValuationInfo(source=summary.valuation_source, label=summary.valuation_label),
        hpi_status=HpiStatusResponse(
            latest_year=status_row.latest_year if status_row else None,
            latest_quarter=status_row.latest_quarter if status_row else None,
        ),
    )


async def _refresh_if_stale(uow: UnitOfWork, refresher: hpi_service.HpiRefresher, assets: Sequence[Asset]) -> None:
    """Schedule the lazy index refresh, but only when a house depends on the index."""
    if any(a.asset_type == "house" for a in assets):
        await hpi_service.ensure_fresh(uow, refresher)


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


@router.get("/families/{family_id}/assets", response_model=AssetListResponse)
async def list_assets(
    family_id: uuid.UUID,
    membership: AssetMembership = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
    refresher: hpi_service.HpiRefresher = Depends(get_hpi_refresher),
) -> AssetListResponse:
    """List the family's assets, newest purchase first, each with its headline numbers."""
    assets = await asset_service.list_assets(uow, family_id)
    today = await asset_analytics.today_for_family(uow, family_id)
    index = await asset_analytics.load_index(uow, assets)  # one query per region, shared by every asset
    links_by_asset: dict[uuid.UUID, list[AssetExpenseLink]] = defaultdict(list)
    for link in await uow.expenses.list_asset_links(family_id, [a.id for a in assets]):
        links_by_asset[link.asset_id].append(link)
    items = []
    for data in await asset_service.load_details(uow, assets):
        asset = data.asset
        summary = asset_analytics.summarize(data, links_by_asset[asset.id], index, today)
        items.append(
            AssetListItem(
                **AssetResponse.model_validate(asset).model_dump(),
                has_loan=data.loan is not None,
                summary=_list_summary(summary),
            )
        )
    await _refresh_if_stale(uow, refresher, assets)
    return AssetListResponse(assets=items)


@router.post("/families/{family_id}/assets", response_model=AssetDetail, status_code=status.HTTP_201_CREATED)
async def create_asset(
    family_id: uuid.UUID,
    body: AssetCreate,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
    refresher: hpi_service.HpiRefresher = Depends(get_hpi_refresher),
) -> AssetDetail:
    """Create an asset, optionally with its loan (admin only)."""
    current_user, _ = membership
    asset = await asset_service.create_asset(
        uow,
        family_id,
        current_user.id,
        fields=body.model_dump(exclude={"loan"}),
        loan=body.loan.model_dump() if body.loan is not None else None,
    )
    await _refresh_if_stale(uow, refresher, [asset])
    return await _detail(uow, family_id, asset.id)


@router.post("/families/{family_id}/assets/hpi-refresh", response_model=HpiRefreshStatusResponse)
async def refresh_house_price_index(
    family_id: uuid.UUID,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
    refresher: hpi_service.HpiRefresher = Depends(get_hpi_refresher),
) -> HpiRefreshStatusResponse:
    """Download the FHFA house price index now and return the refresh status (admin only).

    A failed download is reported in ``last_error``, not as an HTTP error. Refused with 429 (and a
    ``Retry-After`` header) while the last attempt is under an hour old.
    """
    wait = await hpi_service.force_cooldown_remaining(uow, datetime.now(tz=timezone.utc))
    if wait is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The house price index was refreshed recently; try again later",
            headers={"Retry-After": str(max(1, int(wait.total_seconds())))},
        )
    await refresher.run(force=True)
    status_row = await uow.hpi.get_status()
    return (
        HpiRefreshStatusResponse.model_validate(status_row, from_attributes=True)
        if status_row is not None
        else (HpiRefreshStatusResponse())
    )


@router.get("/families/{family_id}/assets/{asset_id}", response_model=AssetDetail)
async def get_asset(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    membership: AssetMembership = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
    refresher: hpi_service.HpiRefresher = Depends(get_hpi_refresher),
) -> AssetDetail:
    """An asset with its loan, corrections, valuations, contributions and computed summary."""
    asset = await asset_service.get_asset(uow, family_id, asset_id)
    detail = await _detail_of(uow, family_id, asset)
    await _refresh_if_stale(uow, refresher, [asset])
    return detail


@router.get("/families/{family_id}/assets/{asset_id}/history", response_model=AssetHistoryResponse)
async def get_asset_history(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    membership: AssetMembership = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
    refresher: hpi_service.HpiRefresher = Depends(get_hpi_refresher),
) -> AssetHistoryResponse:
    """Month-end samples of market value, loan balance, equity and cumulative cash in, for the story chart."""
    asset = await asset_service.get_asset(uow, family_id, asset_id)
    data = await asset_service.load_detail(uow, asset)
    today = await asset_analytics.today_for_family(uow, family_id)
    index = await asset_analytics.load_index(uow, [asset])
    links = await uow.expenses.list_asset_links(family_id, [asset.id])
    points = asset_analytics.history(data, links, index, today)
    await _refresh_if_stale(uow, refresher, [asset])
    return AssetHistoryResponse(points=[AssetHistoryPoint(**vars(p)) for p in points])


@router.put("/families/{family_id}/assets/{asset_id}", response_model=AssetDetail)
async def update_asset(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    body: AssetUpdate,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> AssetDetail:
    """Update the fields present in the body (admin only)."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    await asset_service.update_asset(uow, family_id, asset_id, fields=fields)
    return await _detail(uow, family_id, asset_id)


@router.delete("/families/{family_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> Response:
    """Delete an asset; expenses and recurring rules linked to it are kept, unlinked (admin only)."""
    await asset_service.delete_asset(uow, family_id, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/families/{family_id}/assets/{asset_id}/sell", response_model=AssetDetail)
async def sell_asset(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    body: AssetSellRequest,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> AssetDetail:
    """Mark the asset sold, freezing its numbers as of the sale date (admin only)."""
    await asset_service.sell_asset(
        uow,
        family_id,
        asset_id,
        sold_date=body.sold_date,
        sale_price_cents=body.sale_price_cents,
        selling_costs_cents=body.selling_costs_cents,
        today=await asset_analytics.today_for_family(uow, family_id),
    )
    return await _detail(uow, family_id, asset_id)


@router.delete("/families/{family_id}/assets/{asset_id}/sell", response_model=AssetDetail)
async def unsell_asset(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> AssetDetail:
    """Undo a sale (admin only)."""
    await asset_service.unsell_asset(uow, family_id, asset_id)
    return await _detail(uow, family_id, asset_id)


@router.get("/families/{family_id}/assets/{asset_id}/expenses", response_model=AssetExpensesResponse)
async def list_asset_expenses(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    membership: AssetMembership = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
) -> AssetExpensesResponse:
    """Expenses linked to the asset, newest first."""
    expenses = await asset_service.list_linked_expenses(uow, family_id, asset_id)
    return AssetExpensesResponse(expenses=[ExpenseResponse.model_validate(e) for e in expenses])


# ---------------------------------------------------------------------------
# Loan and balance corrections
# ---------------------------------------------------------------------------


@router.put("/families/{family_id}/assets/{asset_id}/loan", response_model=AssetLoanResponse)
async def upsert_loan(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    body: AssetLoanInput,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> AssetLoanResponse:
    """Create the asset's loan or replace its terms (admin only)."""
    await asset_service.upsert_loan(uow, family_id, asset_id, fields=body.model_dump())
    data = await asset_service.load_detail(uow, await asset_service.get_asset(uow, family_id, asset_id))
    response = _loan_response(data, await asset_analytics.today_for_family(uow, family_id))
    assert response is not None  # just upserted
    return response


@router.delete("/families/{family_id}/assets/{asset_id}/loan", status_code=status.HTTP_204_NO_CONTENT)
async def delete_loan(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> Response:
    """Remove the asset's loan and its balance corrections (admin only)."""
    await asset_service.delete_loan(uow, family_id, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/families/{family_id}/assets/{asset_id}/loan/corrections",
    response_model=LoanCorrectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_correction(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    body: LoanCorrectionCreate,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> LoanCorrectionResponse:
    """Record the loan's real balance on a date (admin only)."""
    correction = await asset_service.add_correction(
        uow, family_id, asset_id, as_of_date=body.as_of_date, balance_cents=body.balance_cents
    )
    return LoanCorrectionResponse.model_validate(correction)


@router.delete(
    "/families/{family_id}/assets/{asset_id}/loan/corrections/{correction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_correction(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    correction_id: uuid.UUID,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> Response:
    """Remove a balance correction (admin only)."""
    await asset_service.delete_correction(uow, family_id, asset_id, correction_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Manual valuations
# ---------------------------------------------------------------------------


@router.post(
    "/families/{family_id}/assets/{asset_id}/valuations",
    response_model=AssetValuationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_valuation(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    body: AssetValuationCreate,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> AssetValuationResponse:
    """Record a manual market value that overrides the estimate from its date on (admin only)."""
    valuation = await asset_service.add_valuation(
        uow, family_id, asset_id, as_of_date=body.as_of_date, value_cents=body.value_cents, note=body.note
    )
    return AssetValuationResponse.model_validate(valuation)


@router.delete(
    "/families/{family_id}/assets/{asset_id}/valuations/{valuation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_valuation(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    valuation_id: uuid.UUID,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> Response:
    """Remove a manual valuation (admin only)."""
    await asset_service.delete_valuation(uow, family_id, asset_id, valuation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Historical contributions
# ---------------------------------------------------------------------------


@router.post(
    "/families/{family_id}/assets/{asset_id}/contributions",
    response_model=AssetContributionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_contribution(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    body: AssetContributionCreate,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> AssetContributionResponse:
    """Record an amount put into the asset before tracking began (admin only)."""
    contribution = await asset_service.add_contribution(uow, family_id, asset_id, fields=body.model_dump())
    return AssetContributionResponse.model_validate(contribution)


@router.put(
    "/families/{family_id}/assets/{asset_id}/contributions/{contribution_id}",
    response_model=AssetContributionResponse,
)
async def update_contribution(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    contribution_id: uuid.UUID,
    body: AssetContributionUpdate,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> AssetContributionResponse:
    """Update the fields present in the body (admin only)."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    contribution = await asset_service.update_contribution(uow, family_id, asset_id, contribution_id, fields=fields)
    return AssetContributionResponse.model_validate(contribution)


@router.delete(
    "/families/{family_id}/assets/{asset_id}/contributions/{contribution_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_contribution(
    family_id: uuid.UUID,
    asset_id: uuid.UUID,
    contribution_id: uuid.UUID,
    membership: AssetMembership = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> Response:
    """Remove a contribution (admin only)."""
    await asset_service.delete_contribution(uow, family_id, asset_id, contribution_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
