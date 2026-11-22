from sqlalchemy import Column, Integer, Float, Text, DateTime, ForeignKey, String
from sqlalchemy.sql import func
from app.database import Base


class WarScoreAdjustment(Base):
    __tablename__ = "war_score_adjustments"
    id = Column(Integer, primary_key=True)
    war_id = Column(Integer, ForeignKey("clan_wars.id", ondelete="CASCADE"), nullable=False, index=True)
    clan_id = Column(Integer, ForeignKey("clans.id", ondelete="CASCADE"), nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    request_id = Column(String(36), nullable=False, unique=True)
    points = Column(Float, nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
