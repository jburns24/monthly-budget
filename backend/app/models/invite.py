"""SQLAlchemy ORM model for the invites table."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Invite(Base):
    """Pending or resolved invitation for a user to join a family."""

    __tablename__ = "invites"

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
    invited_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    family: Mapped["Family"] = relationship(  # noqa: F821
        "Family",
        back_populates="invites",
    )
    invited_user: Mapped["User"] = relationship(  # noqa: F821
        "User",
        foreign_keys=[invited_user_id],
        back_populates="received_invites",
    )
    inviting_user: Mapped["User"] = relationship(  # noqa: F821
        "User",
        foreign_keys=[invited_by],
    )

    __table_args__ = (
        UniqueConstraint("family_id", "invited_user_id", "status", name="uq_invites_family_user_status"),
        CheckConstraint("status IN ('pending', 'accepted', 'declined')", name="ck_invites_status"),
        Index("idx_invites_invited_user", "invited_user_id", "status"),
    )
