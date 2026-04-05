"""SQLAlchemy ORM model for the families table."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Family(Base):
    """A household family group that users can belong to."""

    __tablename__ = "families"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/New_York")
    edit_grace_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    members: Mapped[list["FamilyMember"]] = relationship(  # noqa: F821
        "FamilyMember",
        back_populates="family",
        cascade="all, delete-orphan",
    )
    invites: Mapped[list["Invite"]] = relationship(  # noqa: F821
        "Invite",
        back_populates="family",
        cascade="all, delete-orphan",
    )
    categories: Mapped[list["Category"]] = relationship(  # noqa: F821
        "Category",
        back_populates="family",
        cascade="all, delete-orphan",
    )
