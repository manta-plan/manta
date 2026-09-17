from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from manta.entities.base import Base


class Run(Base):
    __tablename__ = "runs"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    prefect_flow_run_id: Mapped[UUID] = mapped_column(unique=True)
