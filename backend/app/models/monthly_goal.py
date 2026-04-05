"""SQLAlchemy ORM model for the monthly_goals table."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MonthlyGoal(Base):
    """A monthly spending goal for a category within a family."""

    __tablename__ = "monthly_goals"

    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_monthly_goals_amount_positive"),
        UniqueConstraint("family_id", "category_id", "year_month", name="uq_monthly_goals_family_category_month"),
        Index("idx_monthly_goals_family_year_month", "family_id", "year_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default="now()",
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default="now()",
        onupdate=lambda: datetime.now(tz=timezone.utc),
    )

    # Relationships
    family: Mapped["Family"] = relationship(  # noqa: F821
        "Family",
        back_populates="monthly_goals",
    )
    category: Mapped["Category"] = relationship(  # noqa: F821
        "Category",
        back_populates="monthly_goals",
    )
