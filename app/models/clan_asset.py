from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ClanAsset(Base):
    __tablename__ = "clan_assets"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(80), unique=True, nullable=False, index=True)
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    bonus_type = Column(String(50), nullable=False)
    bonus_value = Column(Integer, default=0)
    gold_cost = Column(Integer, default=0)
    iron_cost = Column(Integer, default=0)
    wood_cost = Column(Integer, default=0)
    food_cost = Column(Integer, default=0)
    mithril_cost = Column(Integer, default=0)
    required_influence_level_1 = Column(Integer, default=175, nullable=False)
    required_influence_level_2 = Column(Integer, default=525, nullable=False)
    required_influence_level_3 = Column(Integer, default=1050, nullable=False)
    is_unique = Column(Boolean, default=True)
    is_available = Column(Boolean, default=True)
    max_level = Column(Integer, default=3)
    upgrade_multiplier = Column(Integer, default=5)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owned_items = relationship("ClanOwnedAsset", back_populates="asset", cascade="all, delete-orphan")


class ClanOwnedAsset(Base):
    __tablename__ = "clan_owned_assets"

    id = Column(Integer, primary_key=True, index=True)
    clan_id = Column(Integer, ForeignKey("clans.id"), nullable=False)
    asset_id = Column(Integer, ForeignKey("clan_assets.id"), nullable=False)
    purchased_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    purchased_at = Column(DateTime(timezone=True), server_default=func.now())
    level = Column(Integer, default=1)
    is_active = Column(Boolean, default=False, nullable=False)

    clan = relationship("Clan")
    asset = relationship("ClanAsset", back_populates="owned_items")
    buyer = relationship("User")

    __table_args__ = (
        UniqueConstraint("clan_id", "asset_id", name="uq_clan_asset"),
    )
