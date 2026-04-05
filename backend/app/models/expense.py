"""SQLAlchemy ORM model for the expenses table."""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Expense(Base):
    """An individual expense entry recorded by a family member."""

    __tablename__ = "expenses"

    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_expenses_amount_positive"),
        Index("idx_expenses_family", "family_id"),
        Index("idx_expenses_family_year_month", "family_id", "year_month"),
        Index("idx_expenses_category", "category_id"),
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
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    expense_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    year_month: Mapped[str | None] = mapped_column(String(7), nullable=True)
    receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default="now()",
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default="now()",
        onupdate=datetime.utcnow,
    )

    # Relationships
    family: Mapped["Family"] = relationship(  # noqa: F821
        "Family",
        back_populates="expenses",
    )
    category: Mapped["Category"] = relationship(  # noqa: F821
        "Category",
        back_populates="expenses",
    )
    user: Mapped["User"] = relationship(  # noqa: F821
        "User",
        back_populates="expenses",
    )
