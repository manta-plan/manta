from uuid import UUID

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from manta.entities.base import Base


class Run(Base):
    __tablename__ = "runs"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    prefect_flow_run_id: Mapped[UUID] = mapped_column(unique=True)

    # Playbook runs record what was run and with which settings, for reproducibility.
    # Nullable because runs of plain (non-playbook) deployments predate and coexist
    # with playbook runs. No ondelete: a playbook that has been run cannot be deleted
    # out from under its runs' provenance.
    #
    # TODO: snapshot the playbook doc itself here once playbooks become editable —
    # the playbook row is enough provenance only while playbooks are immutable.
    playbook_id: Mapped[int | None] = mapped_column(ForeignKey("playbooks.id"), default=None)
    playbook_config: Mapped[dict | None] = mapped_column(JSONB, default=None)
    # The run's frozen copy of its input data, keyed inside the app bucket. The
    # input is copied under the run's own prefix before the run starts, so later
    # changes to the source file cannot change what this run read.
    input_key: Mapped[str | None] = mapped_column(Text, default=None)
