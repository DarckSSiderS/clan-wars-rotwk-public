from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.core.auth import (
    get_current_active_user,
    get_current_admin_user,
    get_onboarded_active_user,
)
from app.services.war_service import TerritoryService, ClanWarService, ClanWarParticipantService
from app.schemas.war import (
    Territory, TerritoryCreate, TerritoryUpdate,
    ClanWar, ClanWarCreate, ClanWarParticipant, ClanWarParticipantCreate
)
from app.models.user import User as UserModel
from app.services.operation_service import AdminAuditService
from app.api.v1.campaign_guard import require_campaign_running

router = APIRouter(prefix="/wars", tags=["wars"])

# Территории
@router.get("/territories/", response_model=List[Territory])
async def get_territories(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """Получить список территорий"""
    territory_service = TerritoryService()
    return territory_service.get_territories(db, skip=skip, limit=limit)

@router.get("/territories/available/", response_model=List[Territory])
async def get_available_territories(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """Получить доступные территории"""
    territory_service = TerritoryService()
    return territory_service.get_available_territories(db)

@router.get("/territories/{territory_id:int}", response_model=Territory)
async def get_territory(
    territory_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """Получить территорию по ID"""
    territory_service = TerritoryService()
    return territory_service.get_territory(db, territory_id)

@router.post("/territories/", response_model=Territory)
async def create_territory(
    territory_data: TerritoryCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_admin_user)
):
    """Создать новую территорию"""
    territory_service = TerritoryService()
    return territory_service.create_territory(db, territory_data)

@router.put("/territories/{territory_id:int}", response_model=Territory)
async def update_territory(
    territory_id: int,
    territory_data: TerritoryUpdate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_admin_user)
):
    """Обновить территорию"""
    territory_service = TerritoryService()
    return territory_service.update_territory(db, territory_id, territory_data)

@router.delete("/territories/{territory_id:int}")
async def delete_territory(
    territory_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_admin_user)
):
    """Удалить территорию"""
    territory_service = TerritoryService()
    territory_service.delete_territory(db, territory_id)
    return {"message": "Территория удалена"}

# Клановые войны
@router.get("/")
async def get_wars(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """Получить постоянный журнал активных и завершенных войн"""
    war_service = ClanWarService()
    wars = war_service.get_wars(db, skip=skip, limit=min(limit, 500))
    return [war_service.serialize_war(db, war) for war in wars]

@router.get("/active/")
async def get_active_wars(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """Получить активные войны"""
    war_service = ClanWarService()
    return [war_service.serialize_war(db, war) for war in war_service.get_active_wars(db)]

@router.get("/territory/{territory_id:int}")
async def get_wars_by_territory(
    territory_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """Получить войны по территории"""
    war_service = ClanWarService()
    return [war_service.serialize_war(db, war) for war in war_service.get_wars_by_territory(db, territory_id)]

@router.get("/clan/{clan_id:int}")
async def get_wars_by_clan(
    clan_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """Получить войны клана"""
    war_service = ClanWarService()
    return [war_service.serialize_war(db, war) for war in war_service.get_wars_by_clan(db, clan_id)]

@router.get("/{war_id:int}")
async def get_war(
    war_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """Получить войну по ID"""
    war_service = ClanWarService()
    return war_service.serialize_war(db, war_service.get_war(db, war_id))

@router.post("/")
async def create_war(
    war_data: ClanWarCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_onboarded_active_user)
):
    """Создать новую войну"""
    require_campaign_running(db)
    war_service = ClanWarService()
    war = war_service.create_war(db, war_data, current_user)
    return war_service.serialize_war(db, war)

@router.put("/{war_id:int}/status")
async def update_war_status(
    war_id: int,
    status: str,
    reason: str = Query(..., min_length=3, max_length=500),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_admin_user)
):
    """Совместимый маршрут отмены войны с обязательным аудитом."""
    if status != "canceled":
        raise HTTPException(
            status_code=409,
            detail="Изменяйте сроки и завершайте войну через центр управления",
        )
    war_service = ClanWarService()
    war = war_service.get_war(db, war_id)
    before = {"status": war.status, "winner_clan_id": war.winner_clan_id}
    war_service.cancel_war(db, war_id, refund_attack=True, commit=False)
    AdminAuditService().record(
        db,
        actor_user_id=current_user.id,
        action="war_canceled",
        entity_type="clan_war",
        entity_id=war.id,
        before_data=before,
        after_data={"status": war.status, "winner_clan_id": war.winner_clan_id},
        reason=reason.strip(),
    )
    db.commit()
    return war_service.serialize_war(db, war)

@router.put("/{war_id:int}/end")
async def end_war(
    war_id: int,
    winner_clan_id: int,
    reason: str = Query(..., min_length=3, max_length=500),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_admin_user)
):
    """Совместимый маршрут ручного завершения с обязательным аудитом."""
    war_service = ClanWarService()
    war = war_service.get_war(db, war_id)
    if war.status != "active":
        raise HTTPException(status_code=409, detail="Война уже завершена")
    before = {"status": war.status, "winner_clan_id": war.winner_clan_id}
    war_service._complete_war(db, war, winner_clan_id, commit=False)
    AdminAuditService().record(
        db,
        actor_user_id=current_user.id,
        action="war_finished_manually",
        entity_type="clan_war",
        entity_id=war.id,
        before_data=before,
        after_data={"status": war.status, "winner_clan_id": war.winner_clan_id},
        reason=reason.strip(),
    )
    db.commit()
    return war_service.serialize_war(db, war)

# Участники войн
@router.get("/{war_id:int}/participants/", response_model=List[ClanWarParticipant])
async def get_war_participants(
    war_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """Получить участников войны"""
    participant_service = ClanWarParticipantService()
    return participant_service.get_participants_by_war(db, war_id)

@router.get("/clan/{clan_id:int}/participants/", response_model=List[ClanWarParticipant])
async def get_clan_participants(
    clan_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """Получить участников клана в войнах"""
    participant_service = ClanWarParticipantService()
    return participant_service.get_participants_by_clan(db, clan_id)

@router.post("/participants/", response_model=ClanWarParticipant)
async def add_participant(
    participant_data: ClanWarParticipantCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_admin_user)
):
    """Добавить участника в войну"""
    participant_service = ClanWarParticipantService()
    return participant_service.add_participant(db, participant_data)

@router.delete("/{war_id:int}/participants/{user_id:int}")
async def remove_participant(
    war_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_admin_user)
):
    """Удалить участника из войны"""
    participant_service = ClanWarParticipantService()
    participant_service.remove_participant(db, war_id, user_id)
    return {"message": "Участник удален из войны"}

@router.put("/{war_id:int}/participants/{user_id:int}/stats")
async def update_participant_stats(
    war_id: int,
    user_id: int,
    battles_won: int = None,
    battles_lost: int = None,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_admin_user)
):
    """Обновить статистику участника"""
    participant_service = ClanWarParticipantService()
    return participant_service.update_participant_stats(
        db, war_id, user_id, battles_won, battles_lost
    ) 
