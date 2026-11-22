from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.core.auth import get_current_admin_user, get_onboarded_active_user
from app.core.campaign_mode import is_interseason
from app.models.user import User as UserModel
from app.models.clan import Clan
from app.models.territory import TerritoryOwnershipHistory
from app.models.war import ClanWar
from app.services.clan_economy_service import ClanEconomyService
from app.services.campaign_rule_service import CampaignRuleService
from app.services.war_service import ClanWarService
from app.api.v1.campaign_guard import require_campaign_running
from app.repositories.territory_repository import TerritoryRepository
from app.schemas.territory import (
    TerritoryCreate, 
    TerritoryUpdate, 
    TerritoryResponse, 
    TerritoryWithClans,
    TerritoryStats
    ,TerritoryUpgradeRequest, SeasonStartRequest, TerritoryOwnershipHistoryResponse
)

router = APIRouter()


@router.get("/", response_model=List[TerritoryResponse])
def get_all_territories(db: Session = Depends(get_db)):
    """Получить все территории"""
    repo = TerritoryRepository(db)
    economy = ClanEconomyService()
    if is_interseason(db):
        rows = []
        for territory in repo.get_all():
            owner = territory.owner_clan
            present = owner is not None and not owner.is_deleted
            rows.append(TerritoryResponse.model_validate(territory).model_copy(update={
                'attacking_clans': [], 'defending_clans': [],
                'attacking_clan_names': [], 'defending_clan_names': [],
                'status': 'active' if present else 'neutral',
                'owner_clan_id': owner.id if present else None,
                'owner_clan_name': owner.name if present else None,
                'owner_clan_avatar_url': owner.avatar_url if present else None,
                'owner_clan_map_emblem_url': owner.map_emblem_url if present else None,
                'owner_clan_map_color': territory.owner_clan_map_color if present else None,
                'owner_clan_is_admin': bool(present and owner.is_admin_clan),
            }))
        return rows
    ClanWarService().reconcile_territory_war_sides(db, commit=False)
    rules = CampaignRuleService().get_active(db).values
    economy.settle_all(db, rules=rules)
    territories = repo.get_all()
    for territory in territories:
        economy.prepare_territory(db, territory, rules=rules)
    db.commit()
    return territories


@router.get("/{territory_id:int}/economy")
def get_territory_economy(territory_id: int, db: Session = Depends(get_db)):
    territory = TerritoryRepository(db).get_by_id(territory_id)
    if not territory:
        raise HTTPException(status_code=404, detail="Территория не найдена")
    economy = ClanEconomyService()
    rules = CampaignRuleService().get_active(db).values
    result = economy.get_territory_economy(territory, db, rules=rules)
    result["upgrade_quotes"] = economy.get_upgrade_quotes(
        db,
        territory,
        rules=rules,
    )
    return result


@router.get(
    "/{territory_id:int}/ownership-history",
    response_model=List[TerritoryOwnershipHistoryResponse],
)
def get_territory_ownership_history(
    territory_id: int,
    db: Session = Depends(get_db),
):
    territory = TerritoryRepository(db).get_by_id(territory_id)
    if not territory:
        raise HTTPException(status_code=404, detail="Территория не найдена")
    rows = (
        db.query(TerritoryOwnershipHistory, Clan.name)
        .join(Clan, Clan.id == TerritoryOwnershipHistory.clan_id)
        .filter(TerritoryOwnershipHistory.territory_id == territory_id)
        .order_by(TerritoryOwnershipHistory.started_at.desc())
        .all()
    )
    return [
        {
            "id": history.id,
            "territory_id": history.territory_id,
            "clan_id": history.clan_id,
            "clan_name": clan_name,
            "started_at": history.started_at,
            "ended_at": history.ended_at,
            "war_id": history.war_id,
            "reason": history.reason,
        }
        for history, clan_name in rows
    ]


@router.post("/{territory_id:int}/upgrade")
def upgrade_territory(
    territory_id: int,
    upgrade: TerritoryUpgradeRequest,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    require_campaign_running(db)
    return ClanEconomyService().upgrade_territory(
        db, territory_id, upgrade.upgrade_type, upgrade.levels, current_user
    )


@router.post("/season/start")
def start_new_season(
    request: SeasonStartRequest,
    current_admin: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    require_campaign_running(db)
    return ClanEconomyService().start_new_season(
        db,
        request.starting_influence,
        request.reset_development,
        actor_user_id=current_admin.id,
        season_name=request.name,
    )


@router.get("/stats", response_model=TerritoryStats)
def get_territory_stats(db: Session = Depends(get_db)):
    """Получить статистику территорий"""
    repo = TerritoryRepository(db)
    return repo.get_territory_stats()


@router.get("/{territory_id:int}", response_model=TerritoryResponse)
def get_territory(territory_id: int, db: Session = Depends(get_db)):
    """Получить территорию по ID"""
    repo = TerritoryRepository(db)
    territory = repo.get_by_id(territory_id)
    if not territory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Территория не найдена"
        )
    return territory


@router.get("/by-name/{name}", response_model=TerritoryResponse)
def get_territory_by_name(name: str, db: Session = Depends(get_db)):
    """Получить территорию по имени"""
    repo = TerritoryRepository(db)
    territory = repo.get_by_name(name)
    if not territory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Территория не найдена"
        )
    return territory


@router.get("/by-path-data/{svg_path_data}", response_model=TerritoryResponse)
def get_territory_by_svg_path_data(svg_path_data: str, db: Session = Depends(get_db)):
    """Получить территорию по SVG path data"""
    repo = TerritoryRepository(db)
    territory = repo.get_by_svg_path_data(svg_path_data)
    if not territory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Территория не найдена"
        )
    return territory


@router.get("/region/{region}", response_model=List[TerritoryResponse])
def get_territories_by_region(region: str, db: Session = Depends(get_db)):
    """Получить территории по региону"""
    repo = TerritoryRepository(db)
    territories = repo.get_by_region(region)
    return territories


@router.get("/status/{status}", response_model=List[TerritoryResponse])
def get_territories_by_status(status: str, db: Session = Depends(get_db)):
    """Получить территории по статусу"""
    repo = TerritoryRepository(db)
    territories = repo.get_by_status(status)
    return territories


@router.get("/owner/{clan_id}", response_model=List[TerritoryResponse])
def get_territories_by_owner(clan_id: int, db: Session = Depends(get_db)):
    """Получить территории по владельцу"""
    repo = TerritoryRepository(db)
    territories = repo.get_by_owner_clan(clan_id)
    return territories


@router.post("/", response_model=TerritoryResponse)
def create_territory(
    territory_data: TerritoryCreate,
    current_admin: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Создать новую территорию"""
    repo = TerritoryRepository(db)
    
    # Проверяем, что территория с таким именем не существует
    existing = repo.get_by_name(territory_data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Территория с таким именем уже существует"
        )
    
    # Проверяем, что территория с таким SVG path data не существует
    existing_path = repo.get_by_svg_path_data(territory_data.svg_path_data)
    if existing_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Территория с таким SVG path data уже существует"
        )
    
    territory = repo.create(territory_data)
    return territory


@router.put("/{territory_id:int}", response_model=TerritoryResponse)
def update_territory(
    territory_id: int,
    territory_data: TerritoryUpdate,
    current_admin: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Обновить территорию"""
    repo = TerritoryRepository(db)
    existing = repo.get_by_id(territory_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Территория не найдена"
        )
    changed_fields = territory_data.model_dump(exclude_unset=True)
    before_data = {
        field: (
            value.isoformat()
            if hasattr(value, "isoformat")
            else value
        )
        for field in changed_fields
        if (value := getattr(existing, field, None)) is not None
    }
    territory = repo.update(territory_id, territory_data)
    if not territory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Территория не найдена"
        )
    from app.services.operation_service import AdminAuditService

    AdminAuditService().record(
        db,
        actor_user_id=current_admin.id,
        action="territory_parameters_updated",
        entity_type="territory",
        entity_id=territory.id,
        before_data=before_data,
        after_data={
            field: (
                value.isoformat()
                if hasattr(value, "isoformat")
                else value
            )
            for field in changed_fields
            if (value := getattr(territory, field, None)) is not None
        },
        reason="Редактирование параметров территории на карте",
    )
    db.commit()
    db.refresh(territory)
    return territory


@router.delete("/{territory_id:int}")
def delete_territory(
    territory_id: int,
    current_admin: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Удалить территорию"""
    repo = TerritoryRepository(db)
    success = repo.delete(territory_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Территория не найдена"
        )
    return {"message": "Территория успешно удалена"}


@router.post("/{territory_id:int}/attacking-clans/{clan_id:int}")
def add_attacking_clan(
    territory_id: int,
    clan_id: int,
    current_admin: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Добавить атакующий клан к территории"""
    active_war = db.query(ClanWar.id).filter(
        ClanWar.territory_id == territory_id,
        ClanWar.attacking_clan_id == clan_id,
        ClanWar.status == "active",
    ).first()
    if active_war is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Стороны территории назначаются только через активную войну",
        )
    repo = TerritoryRepository(db)
    success = repo.add_attacking_clan(territory_id, clan_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось добавить атакующий клан"
        )
    return {"message": "Атакующий клан успешно добавлен"}


@router.post("/{territory_id:int}/defending-clans/{clan_id:int}")
def add_defending_clan(
    territory_id: int,
    clan_id: int,
    current_admin: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Добавить защищающий клан к территории"""
    active_war = db.query(ClanWar.id).filter(
        ClanWar.territory_id == territory_id,
        ClanWar.defending_clan_id == clan_id,
        ClanWar.status == "active",
    ).first()
    if active_war is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Стороны территории назначаются только через активную войну",
        )
    repo = TerritoryRepository(db)
    success = repo.add_defending_clan(territory_id, clan_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось добавить защищающий клан"
        )
    return {"message": "Защищающий клан успешно добавлен"}


@router.delete("/{territory_id:int}/clans/{clan_id:int}")
def remove_clan_from_territory(
    territory_id: int,
    clan_id: int,
    current_admin: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Удалить клан с территории"""
    repo = TerritoryRepository(db)
    success = repo.remove_clan_from_territory(territory_id, clan_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось удалить клан с территории"
        )
    return {"message": "Клан успешно удален с территории"} 
