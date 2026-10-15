"""Unit tests for the adapters between asset rows and the pure asset math. No database."""

from datetime import date
from decimal import Decimal

from app.models.house_price_index import HousePriceIndex
from app.services import asset_analytics
from tests.unit.conftest import make_asset, make_user, seed


def _hpi(series, geo, year, quarter, value):
    return HousePriceIndex(series=series, geo_code=geo, year=year, quarter=quarter, index_value=Decimal(value))


async def test_load_index_reads_each_needed_series_once(uow, family_id) -> None:
    user = make_user()
    await seed(
        uow,
        _hpi("zip3", "276", 2024, 1, "100"),
        _hpi("zip3", "276", 2026, 1, "110"),
        _hpi("zip3", "999", 2026, 1, "5"),
        _hpi("state", "NC", 2026, 2, "200"),
    )
    houses = [
        make_asset(family_id, user.id, zip_code="27601", state="NC"),
        make_asset(family_id, user.id, zip_code="27699", state="NC"),
    ]
    calls: list[tuple[str, str]] = []
    original = uow.hpi.get_series

    async def counting(series, geo):
        calls.append((series, geo))
        return await original(series, geo)

    uow.hpi.get_series = counting  # type: ignore[method-assign]

    index = await asset_analytics.load_index(uow, houses)

    assert sorted(calls) == [("state", "NC"), ("zip3", "276")]  # deduplicated, nothing for other regions
    assert index.get("zip3", "276", 2024, 1) == Decimal("100.00")
    assert index.get("zip3", "276", 2025, 1) is None
    assert index.latest("zip3", "276") == (2026, 1)
    assert index.latest("state", "NC") == (2026, 2)
    assert index.latest("zip3", "999") is None


async def test_load_index_ignores_non_houses(uow, family_id) -> None:
    user = make_user()
    car = make_asset(family_id, user.id, asset_type="vehicle")
    calls: list[tuple[str, str]] = []

    async def counting(series, geo):
        calls.append((series, geo))
        return []

    uow.hpi.get_series = counting  # type: ignore[method-assign]

    index = await asset_analytics.load_index(uow, [car])

    assert calls == []
    assert index.latest("zip3", "276") is None


def test_loan_projection_for_a_zero_rate_loan() -> None:
    from app.models.asset import AssetLoan

    loan = AssetLoan(
        original_amount_cents=1_200_000,
        annual_interest_rate=Decimal(0),
        term_months=12,
        first_payment_date=date(2026, 1, 1),
        monthly_payment_cents=None,
        escrow_monthly_cents=0,
    )

    payment, payoff = asset_analytics.loan_projection(loan, [], date(2026, 6, 15))

    assert payment == 100_000
    assert payoff == date(2026, 12, 1)
