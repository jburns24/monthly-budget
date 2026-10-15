from datetime import date
from decimal import Decimal
from typing import Any

from app.services.assets.types import AssetInput, ValuationInput
from app.services.assets.valuation import (
    DefaultValuationProvider,
    DepreciationValuationProvider,
    Factor,
    FlatValuationProvider,
    HpiValuationProvider,
    market_value_as_of,
    quarter_of,
)


class FakeIndex:
    """Dict-backed IndexLookup: data[(series, geo)] = {(year, quarter): value}."""

    def __init__(self, data: dict[tuple[str, str], dict[tuple[int, int], str]]):
        self._data = {k: {q: Decimal(v) for q, v in rows.items()} for k, rows in data.items()}

    def get(self, series, geo_code, year, quarter):
        return self._data.get((series, geo_code), {}).get((year, quarter))

    def latest(self, series, geo_code):
        rows = self._data.get((series, geo_code))
        return max(rows) if rows else None


def house(**overrides) -> AssetInput:
    values: dict[str, Any] = dict(
        asset_type="house",
        purchase_date=date(2020, 5, 10),
        purchase_price_cents=30_000_000,
        state="NC",
        zip_code="27513",
    )
    values.update(overrides)
    return AssetInput(**values)


class RecordingProvider:
    def __init__(self, factor: Factor):
        self._factor = factor
        self.calls: list[tuple[date, date]] = []

    def factor(self, asset, from_date, to_date):
        self.calls.append((from_date, to_date))
        return self._factor


def test_quarter_of():
    assert quarter_of(date(2024, 1, 1)) == (2024, 1)
    assert quarter_of(date(2024, 3, 31)) == (2024, 1)
    assert quarter_of(date(2024, 4, 1)) == (2024, 2)
    assert quarter_of(date(2024, 12, 31)) == (2024, 4)


class TestHpiProvider:
    def test_ratio_is_zip3_index_at_end_over_start(self):
        index = FakeIndex({("zip3", "275"): {(2020, 2): "200.00", (2024, 1): "300.00"}})
        factor = HpiValuationProvider(index).factor(house(), date(2020, 5, 10), date(2024, 2, 1))
        assert factor == Factor(Decimal("1.5"), "fhfa_zip3", "FHFA ZIP3 275 · 2024Q1")

    def test_end_quarter_is_clamped_to_latest_available(self):
        index = FakeIndex({("zip3", "275"): {(2020, 2): "200.00", (2024, 1): "300.00"}})
        factor = HpiValuationProvider(index).factor(house(), date(2020, 5, 10), date(2025, 9, 1))
        assert factor.ratio == Decimal("1.5")
        assert factor.as_of_label == "FHFA ZIP3 275 · 2024Q1"

    def test_start_quarter_beyond_latest_is_clamped_too(self):
        index = FakeIndex({("zip3", "275"): {(2024, 1): "300.00"}})
        factor = HpiValuationProvider(index).factor(house(), date(2025, 1, 1), date(2025, 9, 1))
        assert factor.ratio == Decimal(1)
        assert factor.source == "fhfa_zip3"

    def test_falls_back_to_state_when_zip3_does_not_cover_start(self):
        index = FakeIndex(
            {
                ("zip3", "275"): {(2024, 1): "300.00"},  # series starts after the anchor quarter
                ("state", "NC"): {(2020, 2): "100.00", (2024, 1): "120.00"},
            }
        )
        factor = HpiValuationProvider(index).factor(house(), date(2020, 5, 10), date(2024, 2, 1))
        assert factor == Factor(Decimal("1.2"), "fhfa_state", "FHFA State NC · 2024Q1")

    def test_falls_back_to_state_when_zip3_is_unknown(self):
        index = FakeIndex({("state", "NC"): {(2020, 2): "100.00", (2024, 1): "150.00"}})
        factor = HpiValuationProvider(index).factor(house(), date(2020, 5, 10), date(2024, 2, 1))
        assert factor.source == "fhfa_state"
        assert factor.ratio == Decimal("1.5")

    def test_falls_back_to_state_when_asset_has_no_zip(self):
        index = FakeIndex(
            {("zip3", "275"): {(2020, 2): "1", (2024, 1): "9"}, ("state", "NC"): {(2020, 2): "1", (2024, 1): "2"}}
        )
        factor = HpiValuationProvider(index).factor(house(zip_code=None), date(2020, 5, 10), date(2024, 2, 1))
        assert factor.source == "fhfa_state"
        assert factor.ratio == Decimal(2)

    def test_no_adjustment_when_neither_series_covers_the_start_quarter(self):
        # both series begin after the anchor quarter; ratios are never built across series
        index = FakeIndex({("zip3", "275"): {(2024, 1): "300.00"}, ("state", "NC"): {(2024, 1): "120.00"}})
        factor = HpiValuationProvider(index).factor(house(), date(2020, 5, 10), date(2024, 2, 1))
        assert factor == Factor(Decimal(1), "purchase_price", None)

    def test_no_data_means_no_adjustment(self):
        factor = HpiValuationProvider(FakeIndex({})).factor(house(), date(2020, 5, 10), date(2024, 2, 1))
        assert factor == Factor(Decimal(1), "purchase_price", None)

    def test_zero_start_index_is_treated_as_missing(self):
        index = FakeIndex({("zip3", "275"): {(2020, 2): "0", (2024, 1): "300.00"}})
        assert (
            HpiValuationProvider(index).factor(house(), date(2020, 5, 10), date(2024, 2, 1)).source == "purchase_price"
        )


class TestDepreciationProvider:
    def test_default_rate_is_fifteen_percent_a_year(self):
        asset = house(asset_type="vehicle", annual_depreciation_rate=None)
        factor = DepreciationValuationProvider().factor(asset, date(2020, 1, 1), date(2024, 1, 1))  # 1461 days = 4y
        assert factor.source == "depreciation"
        assert factor.ratio.quantize(Decimal("0.000001")) == Decimal("0.522006")

    def test_asset_rate_overrides_default(self):
        asset = house(asset_type="vehicle", annual_depreciation_rate=Decimal("0.10"))
        factor = DepreciationValuationProvider().factor(asset, date(2020, 1, 1), date(2024, 1, 1))
        assert factor.ratio.quantize(Decimal("0.000001")) == Decimal("0.656100")

    def test_zero_rate_keeps_value(self):
        asset = house(asset_type="vehicle", annual_depreciation_rate=Decimal("0"))
        assert DepreciationValuationProvider().factor(asset, date(2020, 1, 1), date(2024, 1, 1)).ratio == Decimal(1)

    def test_no_elapsed_time_is_no_change(self):
        asset = house(asset_type="vehicle")
        assert DepreciationValuationProvider().factor(asset, date(2020, 1, 1), date(2020, 1, 1)).ratio == Decimal(1)

    def test_end_before_start_is_no_change(self):
        asset = house(asset_type="vehicle")
        assert DepreciationValuationProvider().factor(asset, date(2020, 1, 1), date(2019, 1, 1)).ratio == Decimal(1)


def test_flat_provider_never_adjusts():
    factor = FlatValuationProvider().factor(house(asset_type="other"), date(2020, 1, 1), date(2030, 1, 1))
    assert factor.ratio == Decimal(1)
    assert factor.source == "purchase_price"


class TestDefaultProvider:
    def test_dispatches_by_asset_type(self):
        index = FakeIndex({("zip3", "275"): {(2020, 2): "100", (2024, 1): "200"}})
        provider = DefaultValuationProvider(index)
        start, end = date(2020, 5, 10), date(2024, 2, 1)
        assert provider.factor(house(), start, end).source == "fhfa_zip3"
        assert provider.factor(house(asset_type="vehicle"), start, end).source == "depreciation"
        assert provider.factor(house(asset_type="other"), start, end).ratio == Decimal(1)


class TestMarketValueAsOf:
    def test_purchase_date_is_the_purchase_price(self):
        result = market_value_as_of(house(), [], FlatValuationProvider(), date(2020, 5, 10))
        assert (result.value_cents, result.source, result.as_of_label) == (30_000_000, "purchase_price", None)

    def test_purchase_price_is_scaled_by_the_provider_factor(self):
        provider = RecordingProvider(Factor(Decimal("1.5"), "fhfa_zip3", "FHFA ZIP3 275 · 2024Q1"))
        result = market_value_as_of(house(), [], provider, date(2024, 2, 1))
        assert result.value_cents == 45_000_000
        assert result.source == "fhfa_zip3"
        assert result.as_of_label == "FHFA ZIP3 275 · 2024Q1"
        assert provider.calls == [(date(2020, 5, 10), date(2024, 2, 1))]

    def test_latest_manual_valuation_on_or_before_date_is_the_anchor(self):
        provider = RecordingProvider(Factor(Decimal(1), "purchase_price", None))
        valuations = [
            ValuationInput(date(2021, 1, 1), 31_000_000),
            ValuationInput(date(2023, 1, 1), 40_000_000),
            ValuationInput(date(2025, 1, 1), 50_000_000),
        ]
        result = market_value_as_of(house(), valuations, provider, date(2024, 1, 1))
        assert result.value_cents == 40_000_000
        assert result.source == "manual"
        assert provider.calls == [(date(2023, 1, 1), date(2024, 1, 1))]

    def test_manual_valuation_on_the_date_needs_no_adjustment(self):
        provider = RecordingProvider(Factor(Decimal("2"), "fhfa_zip3", "x"))
        result = market_value_as_of(house(), [ValuationInput(date(2023, 1, 1), 40_000_000)], provider, date(2023, 1, 1))
        assert (result.value_cents, result.source) == (40_000_000, "manual")
        assert provider.calls == []

    def test_manual_anchor_is_adjusted_by_index_growth_since(self):
        provider = RecordingProvider(Factor(Decimal("1.1"), "fhfa_state", "FHFA State NC · 2024Q1"))
        result = market_value_as_of(house(), [ValuationInput(date(2023, 1, 1), 40_000_000)], provider, date(2024, 1, 1))
        assert result.value_cents == 44_000_000
        assert result.source == "fhfa_state"

    def test_manual_valuation_dated_after_the_date_is_ignored(self):
        provider = RecordingProvider(Factor(Decimal(1), "purchase_price", None))
        result = market_value_as_of(house(), [ValuationInput(date(2025, 1, 1), 50_000_000)], provider, date(2024, 1, 1))
        assert result.value_cents == 30_000_000
        assert result.source == "purchase_price"

    def test_value_rounds_half_up_to_cents(self):
        provider = RecordingProvider(Factor(Decimal("1.00005"), "fhfa_zip3", None))
        asset = house(purchase_price_cents=10_000)  # 10000.5 cents
        assert market_value_as_of(asset, [], provider, date(2024, 1, 1)).value_cents == 10_001

    def test_vehicle_depreciates_from_purchase(self):
        asset = house(asset_type="vehicle", purchase_date=date(2020, 1, 1), purchase_price_cents=2_000_000)
        result = market_value_as_of(asset, [], DepreciationValuationProvider(), date(2024, 1, 1))
        assert result.value_cents == 1_044_013  # 2,000,000 * 0.85^4 = 1,044,012.5
        assert result.source == "depreciation"

    def test_sold_asset_is_frozen_at_sale_price(self):
        asset = house(sold_date=date(2024, 6, 1), sale_price_cents=42_000_000, selling_costs_cents=1_000_000)
        provider = RecordingProvider(Factor(Decimal("2"), "fhfa_zip3", "x"))
        on_sale = market_value_as_of(asset, [], provider, date(2024, 6, 1))
        assert (on_sale.value_cents, on_sale.source) == (42_000_000, "sale_price")
        assert market_value_as_of(asset, [], provider, date(2030, 1, 1)).value_cents == 42_000_000
        assert provider.calls == []

    def test_sold_asset_before_sale_uses_the_provider(self):
        asset = house(sold_date=date(2024, 6, 1), sale_price_cents=42_000_000)
        provider = RecordingProvider(Factor(Decimal("1.5"), "fhfa_zip3", "x"))
        assert market_value_as_of(asset, [], provider, date(2024, 5, 31)).value_cents == 45_000_000
