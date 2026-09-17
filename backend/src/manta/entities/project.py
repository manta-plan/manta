from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from manta.entities.base import Base


class Project(Base):
    __tablename__ = "projects"

    name: Mapped[str]
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
