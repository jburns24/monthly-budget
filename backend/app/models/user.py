"""SQLAlchemy ORM model for the users table."""

import uuid
from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """User account, created on first Google OAuth login."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    google_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(String, nullable=False, default="America/New_York")
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    family_memberships: Mapped[list["FamilyMember"]] = relationship(  # noqa: F821
        "FamilyMember",
        back_populates="user",
    )
    received_invites: Mapped[list["Invite"]] = relationship(  # noqa: F821
        "Invite",
        foreign_keys="Invite.invited_user_id",
        back_populates="invited_user",
    )
