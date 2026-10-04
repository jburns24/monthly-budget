"""SQLAlchemy ORM model for the recurring_expenses table."""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RecurringExpense(Base):
    """A schedule that materialises into ordinary expense/income rows as it comes due.

    The rule is configured once. ``next_due_date`` is the next occurrence not yet
    turned into an ``Expense``; ``occurrences_created`` is how many have been, which
    lets each occurrence be derived from ``start_date`` (so a monthly rule anchored
    on the 31st does not drift to the 28th after February).
    """

    __tablename__ = "recurring_expenses"

    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_recurring_expenses_amount_positive"),
        CheckConstraint(
            "frequency IN ('weekly', 'biweekly', 'monthly', 'yearly')",
            name="ck_recurring_expenses_frequency",
        ),
        CheckConstraint("entry_type IN ('expense', 'income')", name="ck_recurring_expenses_entry_type"),
        CheckConstraint(
            "(entry_type = 'expense' AND category_id IS NOT NULL) OR (entry_type = 'income' AND category_id IS NULL)",
            name="ck_recurring_expenses_entry_type_category",
        ),
        Index("idx_recurring_expenses_family", "family_id"),
        Index("idx_recurring_expenses_due", "family_id", "is_active", "next_due_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False, default="expense", server_default="expense")
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    occurrences_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(tz=timezone.utc),
    )
