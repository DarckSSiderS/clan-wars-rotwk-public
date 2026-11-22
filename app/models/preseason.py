"""Выбор следующего сезона без создания активной кампании и таймера."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from app.database import Base


class CampaignPreseason(Base):
    __tablename__ = 'campaign_preseasons'
    source_season_id = Column(Integer, ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), primary_key=True)
    source_archive_checksum = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default='open')
    opened_at = Column(DateTime(timezone=True), nullable=False)
    initial_owners = Column(JSON, nullable=False)
    qualifications = Column(JSON, nullable=False, default=dict)
    launched_season_id = Column(Integer, ForeignKey('campaign_seasons.id', ondelete='RESTRICT'))


class CampaignPreseasonChoice(Base):
    __tablename__ = 'campaign_preseason_choices'
    id = Column(Integer, primary_key=True)
    preparation_id = Column(Integer, ForeignKey('campaign_preseasons.source_season_id', ondelete='RESTRICT'), nullable=False)
    clan_id = Column(Integer, ForeignKey('clans.id', ondelete='SET NULL'), nullable=True)
    selected_lands = Column(JSON, nullable=False, default=list)
    selected_relics = Column(JSON, nullable=False, default=list)
    lands_chosen_at = Column(DateTime(timezone=True))
    relics_chosen_at = Column(DateTime(timezone=True))
    revision = Column(Integer, nullable=False, default=1)
    __table_args__ = (UniqueConstraint('preparation_id', 'clan_id', name='uq_preseason_choice_clan'),)


class CampaignPreseasonCandidate(Base):
    """Снимок достигнутой четвёрки в транзакции вступления или привязки UUID."""
    __tablename__ = 'campaign_preseason_candidates'
    id = Column(Integer, primary_key=True)
    # Ссылка на неизменяемый исходный сезон не конфликтует с блокировкой регистрации.
    preparation_id = Column(Integer, ForeignKey('campaign_seasons.id', ondelete='RESTRICT'), nullable=False, index=True)
    clan_id = Column(Integer, nullable=False)
    qualified_at = Column(DateTime(timezone=True), nullable=False)
    selected_four = Column(JSON, nullable=False)
