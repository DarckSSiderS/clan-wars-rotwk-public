"""Persistence owned exclusively by the Palantir integration."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from app.database import Base


class DiscordLink(Base):
    __tablename__ = "discord_links"
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    discord_user_id = Column(String(20), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False)


class DiscordLinkCode(Base):
    __tablename__ = "discord_link_codes"
    discord_user_id = Column(String(20), primary_key=True)
    code_hash = Column(String(64), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class DiscordResource(Base):
    __tablename__ = "discord_resources"
    guild_id = Column(String(20), primary_key=True)
    key = Column(String(160), primary_key=True)
    value = Column(JSON, nullable=False)


class DiscordDelivery(Base):
    __tablename__ = "discord_deliveries"
    guild_id = Column(String(20), primary_key=True)
    key = Column(String(200), primary_key=True)
    delivered_at = Column(DateTime(timezone=True), nullable=False)
