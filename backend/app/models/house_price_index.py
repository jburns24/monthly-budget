"""SQLAlchemy ORM models for the cached FHFA house price index and its refresh bookkeeping."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

HPI_SERIES = ("zip3", "state")


class HousePriceIndex(Base):
    """One quarterly index observation for a region.

    ``series`` is ``zip3`` (``geo_code`` like ``'010'``) or ``state`` (``'NC'``). Rows are replaced
    wholesale per series on refresh, so there is no surrogate key.
    """

    __tablename__ = "house_price_index"

    __table_args__ = (
        CheckConstraint("series IN ('zip3', 'state')", name="ck_house_price_index_series"),
        CheckConstraint("quarter BETWEEN 1 AND 4", name="ck_house_price_index_quarter"),
    )

    series: Mapped[str] = mapped_column(String(10), primary_key=True)
    geo_code: Mapped[str] = mapped_column(String(3), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    quarter: Mapped[int] = mapped_column(Integer, primary_key=True)
    index_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)


class HpiRefreshStatus(Base):
    """Single-row (``id = 1``) record of the last attempt to refresh the house price index."""

    __tablename__ = "hpi_refresh_status"

    __table_args__ = (CheckConstraint("id = 1", name="ck_hpi_refresh_status_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    last_attempt_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    latest_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latest_quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
