from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import ARRAY, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from manta.entities.base import Base


class DatarecordSessionStatus(StrEnum):
    STOPPED = "stopped"
    ACTIVE = "active"


class DatarecordSession(Base):
    __tablename__ = "datarecord_sessions"
    __table_args__ = (UniqueConstraint("user_id", "project_id"),)

    updated_at = None

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    status: Mapped[str]
    generation: Mapped[int]
    quack_token: Mapped[str]
    api_secret: Mapped[str]
    instance_ref: Mapped[str | None]
    endpoint: Mapped[str | None]
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DatarecordSessionRegistration(Base):
    __tablename__ = "datarecord_session_registrations"
    __table_args__ = (UniqueConstraint("datarecord_session_id", "name"),)

    updated_at = None

    datarecord_session_id: Mapped[int] = mapped_column(
        ForeignKey("datarecord_sessions.id", ondelete="CASCADE")
    )
    name: Mapped[str]
    kind: Mapped[str]
    store: Mapped[str]
    revision_uuid: Mapped[UUID]
    packs: Mapped[list[str]] = mapped_column(ARRAY(Text))
