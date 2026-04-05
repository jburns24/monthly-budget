"""SQLAlchemy ORM model for the categories table."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Category(Base):
    """A budget category belonging to a family."""

    __tablename__ = "categories"

    __table_args__ = (
        UniqueConstraint("family_id", "name", name="uq_categories_family_name"),
        Index("idx_categories_family", "family_id"),
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
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default="now()",
    )

    # Relationships
    family: Mapped["Family"] = relationship(  # noqa: F821
        "Family",
        back_populates="categories",
    )
    expenses: Mapped[list["Expense"]] = relationship(  # noqa: F821
        "Expense",
        back_populates="category",
        passive_deletes=True,
    )
    monthly_goals: Mapped[list["MonthlyGoal"]] = relationship(  # noqa: F821
        "MonthlyGoal",
        back_populates="category",
        passive_deletes=True,
    )
