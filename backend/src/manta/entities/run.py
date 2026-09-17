from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from manta.entities.base import Base


class Run(Base):
    __tablename__ = "runs"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    prefect_flow_run_id: Mapped[UUID] = mapped_column(unique=True)

    # Playbook runs only (NULL for the legacy pi-digit-stats runs). Everything a
    # run was made of is persisted here — the playbook document as submitted, the
    # settings, and where the input/outputs live — so a run stays reproducible
    # from Manta's own records, independent of Prefect's retention.
    playbook_name: Mapped[str | None] = mapped_column(default=None)
    playbook_doc: Mapped[dict | None] = mapped_column(JSONB, default=None)
    playbook_config: Mapped[dict | None] = mapped_column(JSONB, default=None)
    input_url: Mapped[str | None] = mapped_column(default=None)
    output_prefix: Mapped[str | None] = mapped_column(default=None)
