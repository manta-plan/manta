from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from manta.entities.base import Base


class Project(Base):
    __tablename__ = "projects"

    name: Mapped[str]
    description: Mapped[str | None] = mapped_column(Text)
