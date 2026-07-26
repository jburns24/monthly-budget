"""SQLAlchemy ORM model for the receipts table."""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Receipt(Base):
    """A receipt image uploaded by a family member, with Claude-extracted data."""

    __tablename__ = "receipts"

    __table_args__ = (
        CheckConstraint("status IN ('processing','completed','failed')", name="ck_receipts_status"),
        Index("idx_receipts_family", "family_id"),
        Index("idx_receipts_status", "status"),
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
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    parsed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    parsed_total_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parsed_merchant: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    family: Mapped["Family"] = relationship(  # noqa: F821
        "Family",
        back_populates="receipts",
    )
    uploader: Mapped["User"] = relationship(  # noqa: F821
        "User",
        foreign_keys=[uploaded_by],
        back_populates="uploaded_receipts",
    )
    expense: Mapped["Expense | None"] = relationship(  # noqa: F821
        "Expense",
        primaryjoin="Receipt.id == foreign(Expense.receipt_id)",
        back_populates="receipt",
        uselist=False,
    )
