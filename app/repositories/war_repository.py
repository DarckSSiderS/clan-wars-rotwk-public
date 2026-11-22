from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime

from app.models.territory import Territory
from app.models.war import ClanWar, ClanWarParticipant, ClanTimeout
from app.repositories.base import BaseRepository


class WarTerritoryRepository(BaseRepository[Territory]):
    """Репозиторий для работы с территориями в контексте войн"""
    
    def __init__(self):
        super().__init__(Territory)
    
    def get_by_name(self, db: Session, name: str) -> Optional[Territory]:
        """Получить территорию по названию"""
        return db.query(Territory).filter(Territory.name == name).first()
    
    def get_available_territories(self, db: Session) -> List[Territory]:
        """Получить все доступные территории"""
        return db.query(Territory).filter(
            Territory.owner_clan_id.is_(None),
            Territory.status == "neutral"
        ).all()


class ClanWarRepository(BaseRepository[ClanWar]):
    """Репозиторий для работы с клановыми войнами"""
    
    def __init__(self):
        super().__init__(ClanWar)
    
    def get_active_wars(self, db: Session) -> List[ClanWar]:
        """Получить все активные войны"""
        return (
            db.query(ClanWar)
            .filter(ClanWar.status == "active")
            .order_by(ClanWar.started_at.desc(), ClanWar.id.desc())
            .all()
        )

    def get_wars(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[ClanWar]:
        """Получить активные и завершенные войны для общего журнала."""
        return (
            db.query(ClanWar)
            .order_by(ClanWar.started_at.desc(), ClanWar.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_active_attack_by_clan(self, db: Session, clan_id: int) -> Optional[ClanWar]:
        """Клан может атаковать только одну территорию одновременно"""
        return db.query(ClanWar).filter(
            ClanWar.attacking_clan_id == clan_id,
            ClanWar.status == "active"
        ).first()

    def get_active_wars_for_clan(self, db: Session, clan_id: int) -> List[ClanWar]:
        return db.query(ClanWar).filter(
            ClanWar.status == "active",
            or_(
                ClanWar.attacking_clan_id == clan_id,
                ClanWar.defending_clan_id == clan_id
            )
        ).all()
    
    def get_wars_by_territory(self, db: Session, territory_id: int) -> List[ClanWar]:
        """Получить войны по территории"""
        return db.query(ClanWar).filter(ClanWar.territory_id == territory_id).all()
    
    def get_wars_by_clan(self, db: Session, clan_id: int) -> List[ClanWar]:
        """Получить войны клана"""
        return db.query(ClanWar).filter(
            or_(
                ClanWar.attacking_clan_id == clan_id,
                ClanWar.defending_clan_id == clan_id
            )
        ).all()


class ClanWarParticipantRepository(BaseRepository[ClanWarParticipant]):
    """Репозиторий для работы с участниками войн"""
    
    def __init__(self):
        super().__init__(ClanWarParticipant)
    
    def get_participants_by_war(self, db: Session, war_id: int) -> List[ClanWarParticipant]:
        """Получить участников войны"""
        return db.query(ClanWarParticipant).filter(ClanWarParticipant.war_id == war_id).all()
    
    def get_participants_by_clan(self, db: Session, clan_id: int) -> List[ClanWarParticipant]:
        """Получить участников клана в войнах"""
        return db.query(ClanWarParticipant).filter(ClanWarParticipant.clan_id == clan_id).all()
    
    def get_participant_by_user_and_war(self, db: Session, user_id: int, war_id: int) -> Optional[ClanWarParticipant]:
        """Получить участника по пользователю и войне"""
        return db.query(ClanWarParticipant).filter(
            and_(
                ClanWarParticipant.user_id == user_id,
                ClanWarParticipant.war_id == war_id
            )
        ).first()

    def get_active_participant(self, db: Session, user_id: int, war_id: int) -> Optional[ClanWarParticipant]:
        return db.query(ClanWarParticipant).filter(
            ClanWarParticipant.user_id == user_id,
            ClanWarParticipant.war_id == war_id,
            ClanWarParticipant.is_active == True
        ).first()

    def get_user_active_participations(self, db: Session, user_id: int, clan_id: int) -> List[ClanWarParticipant]:
        return db.query(ClanWarParticipant).join(ClanWar).filter(
            ClanWarParticipant.user_id == user_id,
            ClanWarParticipant.clan_id == clan_id,
            ClanWarParticipant.is_active == True,
            ClanWar.status == "active"
        ).all()


class ClanTimeoutRepository(BaseRepository[ClanTimeout]):
    """Репозиторий для работы с таймаутами кланов"""
    
    def __init__(self):
        super().__init__(ClanTimeout)
    
    def get_active_timeouts(self, db: Session) -> List[ClanTimeout]:
        """Получить активные таймауты"""
        return db.query(ClanTimeout).filter(ClanTimeout.timeout_until > datetime.utcnow()).all()
    
    def get_timeout_by_clan(self, db: Session, clan_id: int) -> Optional[ClanTimeout]:
        """Получить таймаут клана"""
        return db.query(ClanTimeout).filter(
            and_(
                ClanTimeout.clan_id == clan_id,
                ClanTimeout.timeout_until > datetime.utcnow()
            )
        ).first() 

    def get_timeout_by_user(self, db: Session, user_id: int) -> Optional[ClanTimeout]:
        """Получить активный таймаут пользователя на вступление в кланы"""
        return db.query(ClanTimeout).filter(
            ClanTimeout.user_id == user_id,
            ClanTimeout.timeout_until > datetime.utcnow()
        ).order_by(ClanTimeout.timeout_until.desc()).first()
