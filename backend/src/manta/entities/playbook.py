from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from manta.entities.base import Base


class Playbook(Base):
    __tablename__ = "playbooks"

    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    # The playbook document (steps, wiring, conditions), in the shape defined by
    # manta_playbooks.yaml_io.PlaybookDoc. Stored as the document rather than
    # normalized tables so what runs is exactly what was authored.
    doc: Mapped[dict] = mapped_column(JSONB)
    # A ready-to-run set of settings for this playbook; the starting point a user
    # edits rather than a schema-derived skeleton.
    default_config: Mapped[dict] = mapped_column(JSONB, default=dict)
