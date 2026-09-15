from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped

from manta.entities.base import Base


class User(Base):
    __tablename__ = "users"
    # Assumes a single IdP for now; if that changes, idp_subject alone is not
    # globally unique and this needs to go back to a separate credentials table.
    __table_args__ = (UniqueConstraint("idp_subject", "idp_source"),)

    # A cached copy of the IdP's `preferred_username` claim - not an identity
    # key (that's idp_subject) and not guaranteed unique or stable: the IdP
    # can rename a user, and our copy won't reflect it.
    username: Mapped[str]
    # the openid connect subject that authenticates to this user
    idp_subject: Mapped[str]
    # the openid connect source that authenticates to this user
    idp_source: Mapped[str]
