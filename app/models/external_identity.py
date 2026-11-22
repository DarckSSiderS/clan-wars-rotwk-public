from hashlib import sha256
import unicodedata

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func

from app.database import Base


def canonical_nickname_key(nickname: str) -> str:
    canonical = unicodedata.normalize("NFKC", str(nickname).strip()).casefold()
    return sha256(canonical.encode("utf-8")).hexdigest()


class ExternalPlayerIdentity(Base):
    __tablename__ = "external_player_identities"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source = Column(String(40), nullable=False, default="bfmeladder")
    external_uuid = Column(String(80), nullable=False)
    current_nickname = Column(String(120), nullable=False)
    current_nickname_key = Column(
        String(64), nullable=False, index=True
    )
    verification_status = Column(String(20), nullable=False, default="unverified")
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="external_identities")
    aliases = relationship(
        "ExternalPlayerAlias",
        back_populates="identity",
        cascade="all, delete-orphan",
        order_by="ExternalPlayerAlias.first_seen_at",
    )

    __table_args__ = (
        UniqueConstraint("source", "external_uuid", name="uq_external_identity_source_uuid"),
        UniqueConstraint("user_id", "source", name="uq_external_identity_user_source"),
    )

    @validates("current_nickname")
    def update_current_nickname_key(self, _key: str, value: str) -> str:
        self.current_nickname_key = canonical_nickname_key(value)
        return value


class ExternalPlayerAlias(Base):
    __tablename__ = "external_player_aliases"

    id = Column(Integer, primary_key=True)
    identity_id = Column(
        Integer,
        ForeignKey("external_player_identities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nickname = Column(String(120), nullable=False)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    identity = relationship("ExternalPlayerIdentity", back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("identity_id", "nickname", name="uq_external_identity_alias"),
    )
