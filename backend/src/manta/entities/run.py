from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from manta.entities.base import Base


class Run(Base):
    __tablename__ = "runs"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    prefect_flow_run_id: Mapped[UUID] = mapped_column(unique=True)

    # Everything a run was made of is persisted here — the playbook document as
    # submitted, the settings, and where the input/outputs live — so a run stays
    # reproducible from Manta's own records, independent of Prefect's retention.
    playbook_name: Mapped[str]
    playbook_doc: Mapped[dict] = mapped_column(JSONB)
    playbook_config: Mapped[dict] = mapped_column(JSONB)
    input_url: Mapped[str]
    output_prefix: Mapped[str]
