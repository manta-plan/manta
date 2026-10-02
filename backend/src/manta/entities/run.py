from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from manta.entities.base import Base


class Run(Base):
    __tablename__ = "runs"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    prefect_flow_run_id: Mapped[UUID] = mapped_column(unique=True)
    # TODO(post-MVP): once ephemeral playbooks are introduced, replace this column
    # with a separate playbooks table holding all of a playbook's data, referenced
    # from here. A bare library playbook name is fine for the MVP.
    playbook: Mapped[str]
