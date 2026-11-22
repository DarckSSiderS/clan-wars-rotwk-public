from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text

from app.database import Base


class CampaignSeasonArchive(Base):
    __tablename__ = "campaign_season_archives"

    season_id = Column(Integer, ForeignKey("campaign_seasons.id"), primary_key=True)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    schema_version = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False)
    map_svg = Column(Text, nullable=False)
    checksum = Column(String(64), nullable=False)
