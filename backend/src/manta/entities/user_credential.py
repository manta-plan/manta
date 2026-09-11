from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from manta.entities.base import Base


class UserCredential(Base):
    __tablename__ = "user_credentials"
    # idp_subject is only unique per idp_source, not globally
    __table_args__ = (UniqueConstraint("idp_subject", "idp_source"),)

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # the openid connect subject that authenticates to this user
    idp_subject: Mapped[str]
    # the openid connect source that authenticates to this user
    # a user may have multiple credentials, one per idp they've linked
    idp_source: Mapped[str]
