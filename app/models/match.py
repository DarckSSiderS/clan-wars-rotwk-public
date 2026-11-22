from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey, Index, JSON, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(String, unique=True, index=True)  # ID матча с bfmeladder.com
    winner_player = Column(String, nullable=False)
    winner_faction = Column(String, nullable=False)
    loser_player = Column(String, nullable=False)
    loser_faction = Column(String, nullable=False)
    match_date = Column(DateTime, nullable=False)  # Дата матча
    duration = Column(String, nullable=True)  # Длительность матча
    game_mode = Column(String, nullable=True)  # 1 vs 1, 2 vs 2, etc.
    map_name = Column(String, nullable=True)  # Название карты
    patch_version = Column(String, nullable=True)  # Версия патча
    is_live = Column(Boolean, default=False)  # LIVE матч или завершенный
    
    # Новые поля из API
    arena_id = Column(String, nullable=True)  # ArenaId
    patch_id = Column(String, nullable=True)  # PatchId
    patch_name = Column(String, nullable=True)  # PatchName
    game_name = Column(String, nullable=True)  # GameName (BFME1, BFME2, etc.)
    map_id = Column(String, nullable=True)  # MapId
    map_preview_source = Column(String, nullable=True)  # MapPreviewSource
    gamemode_name = Column(String, nullable=True)  # GamemodeName
    elo_delta = Column(Integer, nullable=True)  # EloDelta
    downloads = Column(Integer, nullable=True)  # Downloads
    likes = Column(Text, nullable=True)  # Likes (JSON array)
    comments = Column(Text, nullable=True)  # Comments (JSON array)
    replay_download_url = Column(String, nullable=True)  # Ссылка на скачивание реплея
    replay_local_path = Column(String(500), nullable=True)
    replay_file_size = Column(Integer, nullable=True)
    replay_sha256 = Column(String(64), nullable=True)
    replay_download_status = Column(String(24), nullable=True)
    replay_download_error = Column(Text, nullable=True)
    replay_downloaded_at = Column(DateTime(timezone=True), nullable=True)
    source_payload = Column(JSON, nullable=True)
    is_valid = Column(Boolean, nullable=True)  # IsValid
    is_qualification_round = Column(Boolean, nullable=True)  # IsQualificationRound
    
    # UUID игроков
    winner_player_uuid = Column(String, nullable=True)  # PlayerAccountUuid победителя
    loser_player_uuid = Column(String, nullable=True)  # PlayerAccountUuid проигравшего
    
    # Индексы фракций
    winner_faction_index = Column(Integer, nullable=True)  # FactionIndex победителя
    loser_faction_index = Column(Integer, nullable=True)  # FactionIndex проигравшего
    
    # Ранги игроков
    winner_old_rank = Column(Integer, nullable=True)  # OldRank победителя
    winner_new_rank = Column(Integer, nullable=True)  # NewRank победителя
    loser_old_rank = Column(Integer, nullable=True)  # OldRank проигравшего
    loser_new_rank = Column(Integer, nullable=True)  # NewRank проигравшего

    # Снимок публичного Elo из профиля BFME Arena в момент импорта матча.
    winner_elo = Column(Float, nullable=True)
    loser_elo = Column(Float, nullable=True)
    rating_patch_family = Column(String(20), nullable=True)
    ratings_captured_at = Column(DateTime(timezone=True), nullable=True)
    rating_source = Column(String(40), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    participants = relationship(
        "MatchParticipant",
        back_populates="match",
        cascade="all, delete-orphan",
        order_by="MatchParticipant.team, MatchParticipant.id",
    )
    
    # Индексы для быстрого поиска
    __table_args__ = (
        Index('ix_match_date', 'match_date'),
        Index('ix_match_players', 'winner_player', 'loser_player'),
        Index('ix_match_factions', 'winner_faction', 'loser_faction'),
        Index('ix_match_patch', 'patch_version'),
        Index('ix_match_game', 'game_name'),
        Index('ix_match_arena', 'arena_id'),
    )


class MatchParticipant(Base):
    __tablename__ = "match_participants"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    nickname = Column(String, nullable=False)
    player_uuid = Column(String, nullable=True)
    faction = Column(String, nullable=True)
    faction_index = Column(Integer, nullable=True)
    team = Column(Integer, nullable=False, default=0)
    is_winner = Column(Boolean, nullable=False, default=False)
    is_observer = Column(Boolean, nullable=False, default=False)
    old_rank = Column(Integer, nullable=True)
    new_rank = Column(Integer, nullable=True)
    elo = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    match = relationship("Match", back_populates="participants")

    __table_args__ = (
        UniqueConstraint("match_id", "nickname", name="uq_match_participant_nickname"),
        Index("ix_match_participants_match_team", "match_id", "team"),
        Index("ix_match_participants_nickname", "nickname"),
        Index("ix_match_participants_uuid", "player_uuid"),
    )
