"""Market value estimates, via swappable valuation providers.

A provider answers one question: by what ratio does an asset's value change between two
dates? The anchor value (latest manual valuation, else the purchase price) is scaled by
that ratio. A factor whose source is ``"purchase_price"`` means "no adjustment available".
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from typing import Protocol

from app.services.assets.types import AssetInput, IndexLookup, ValuationInput, round_cents

DEFAULT_DEPRECIATION_RATE = Decimal("0.15")
_DAYS_PER_YEAR = Decimal("365.25")
_NO_ADJUSTMENT = "purchase_price"


@dataclass(frozen=True)
class Factor:
    ratio: Decimal
    source: str  # "fhfa_zip3" | "fhfa_state" | "depreciation" | "purchase_price" (no adjustment)
    as_of_label: str | None = None


@dataclass(frozen=True)
class MarketValue:
    value_cents: int
    source: str  # "manual" | "fhfa_zip3" | "fhfa_state" | "depreciation" | "purchase_price" | "sale_price"
    as_of_label: str | None = None


class ValuationProvider(Protocol):
    def factor(self, asset: AssetInput, from_date: date, to_date: date) -> Factor: ...


def quarter_of(d: date) -> tuple[int, int]:
    return d.year, (d.month - 1) // 3 + 1


class HpiValuationProvider:
    """FHFA index ratio: the asset's ZIP3 series, else its state series, else no adjustment."""

    def __init__(self, index_lookup: IndexLookup) -> None:
        self._index = index_lookup

    def factor(self, asset: AssetInput, from_date: date, to_date: date) -> Factor:
        candidates: list[tuple[str, str, str, str]] = []
        if asset.zip_code:
            candidates.append(("zip3", asset.zip_code[:3], "fhfa_zip3", "FHFA ZIP3"))
        if asset.state:
            candidates.append(("state", asset.state, "fhfa_state", "FHFA State"))
        for series, geo_code, source, label in candidates:
            factor = self._series_factor(series, geo_code, source, label, from_date, to_date)
            if factor is not None:
                return factor
        return Factor(Decimal(1), _NO_ADJUSTMENT, None)

    def _series_factor(
        self, series: str, geo_code: str, source: str, label: str, from_date: date, to_date: date
    ) -> Factor | None:
        latest = self._index.latest(series, geo_code)
        if latest is None:
            return None
        start_q = min(quarter_of(from_date), latest)
        end_q = min(quarter_of(to_date), latest)
        start_index = self._index.get(series, geo_code, *start_q)
        end_index = self._index.get(series, geo_code, *end_q)
        if start_index is None or end_index is None or start_index == 0:
            return None
        return Factor(end_index / start_index, source, f"{label} {geo_code} · {end_q[0]}Q{end_q[1]}")


class DepreciationValuationProvider:
    """Declining balance: ``(1 - rate) ** (days / 365.25)``, with a per-asset rate (default 15%/yr)."""

    def factor(self, asset: AssetInput, from_date: date, to_date: date) -> Factor:
        rate = DEFAULT_DEPRECIATION_RATE if asset.annual_depreciation_rate is None else asset.annual_depreciation_rate
        days = (to_date - from_date).days
        if days <= 0:
            return Factor(Decimal(1), "depreciation", None)
        with localcontext() as ctx:
            ctx.prec = 40
            ratio = (1 - rate) ** (Decimal(days) / _DAYS_PER_YEAR)
        return Factor(ratio, "depreciation", None)


class FlatValuationProvider:
    def factor(self, asset: AssetInput, from_date: date, to_date: date) -> Factor:
        return Factor(Decimal(1), _NO_ADJUSTMENT, None)


class DefaultValuationProvider:
    """Picks the provider by asset type: house -> FHFA index, vehicle -> depreciation, other -> flat."""

    def __init__(self, index_lookup: IndexLookup) -> None:
        self._house = HpiValuationProvider(index_lookup)
        self._vehicle = DepreciationValuationProvider()
        self._flat = FlatValuationProvider()

    def factor(self, asset: AssetInput, from_date: date, to_date: date) -> Factor:
        if asset.asset_type == "house":
            return self._house.factor(asset, from_date, to_date)
        if asset.asset_type == "vehicle":
            return self._vehicle.factor(asset, from_date, to_date)
        return self._flat.factor(asset, from_date, to_date)


def market_value_as_of(
    asset: AssetInput, manual_valuations: Sequence[ValuationInput], provider: ValuationProvider, d: date
) -> MarketValue:
    """Estimated value on ``d``; frozen at the sale price once the asset is sold."""
    if asset.sold_date is not None and asset.sale_price_cents is not None and d >= asset.sold_date:
        return MarketValue(asset.sale_price_cents, "sale_price", None)

    manual = [v for v in manual_valuations if v.as_of_date <= d]
    if manual:
        anchor = max(manual, key=lambda v: v.as_of_date)
        anchor_date, anchor_cents, anchor_source = anchor.as_of_date, anchor.value_cents, "manual"
    else:
        anchor_date, anchor_cents, anchor_source = asset.purchase_date, asset.purchase_price_cents, _NO_ADJUSTMENT

    if anchor_date >= d:
        return MarketValue(anchor_cents, anchor_source, None)
    factor = provider.factor(asset, anchor_date, d)
    value = round_cents(Decimal(anchor_cents) * factor.ratio)
    if factor.source == _NO_ADJUSTMENT:
        return MarketValue(value, anchor_source, None)
    return MarketValue(value, factor.source, factor.as_of_label)
