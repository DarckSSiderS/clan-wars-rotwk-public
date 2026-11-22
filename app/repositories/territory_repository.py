from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from app.models.territory import Territory, TerritoryAttackingClans, TerritoryDefendingClans
from app.schemas.territory import TerritoryCreate, TerritoryUpdate
from app.services.clan_influence_service import ClanInfluenceService
from app.services.territory_ownership_service import TerritoryOwnershipService


class TerritoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> List[Territory]:
        return self.db.query(Territory).all()

    def get_by_id(self, territory_id: int) -> Optional[Territory]:
        return self.db.query(Territory).filter(Territory.id == territory_id).first()

    def get_by_name(self, name: str) -> Optional[Territory]:
        return self.db.query(Territory).filter(Territory.name == name).first()

    def get_by_svg_path_data(self, svg_path_data: str) -> Optional[Territory]:
        return self.db.query(Territory).filter(Territory.svg_path_data == svg_path_data).first()

    def get_by_region(self, region: str) -> List[Territory]:
        return self.db.query(Territory).filter(Territory.region == region).all()

    def get_by_owner_clan(self, clan_id: int) -> List[Territory]:
        return self.db.query(Territory).filter(Territory.owner_clan_id == clan_id).all()

    def get_by_status(self, status: str) -> List[Territory]:
        return self.db.query(Territory).filter(Territory.status == status).all()

    def get_contested_territories(self) -> List[Territory]:
        return self.db.query(Territory).filter(Territory.status == 'contested').all()

    def get_neutral_territories(self) -> List[Territory]:
        return self.db.query(Territory).filter(Territory.status == 'neutral').all()

    def get_active_territories(self) -> List[Territory]:
        return self.db.query(Territory).filter(Territory.status == 'active').all()

    def create(self, territory_data: TerritoryCreate) -> Territory:
        territory = Territory(**territory_data.dict())
        self.db.add(territory)
        self.db.commit()
        self.db.refresh(territory)
        return territory

    def update(self, territory_id: int, territory_data: TerritoryUpdate) -> Optional[Territory]:
        territory = self.get_by_id(territory_id)
        if not territory:
            return None
        
        update_data = territory_data.model_dump(exclude_unset=True)
        influence_changed = "influence_value" in update_data
        if "owner_clan_id" in update_data:
            TerritoryOwnershipService().transfer(
                self.db,
                territory,
                update_data.pop("owner_clan_id"),
                reason="admin_update",
            )
        for field, value in update_data.items():
            setattr(territory, field, value)

        if territory.has_port is False:
            territory.port_level = 0
            territory.fleet_level = 0
        elif (territory.fleet_level or 0) > (territory.port_level or 0):
            territory.fleet_level = territory.port_level or 0
        territory.strategic_value = territory.calculate_strategic_value()
        self.db.flush()
        if influence_changed and territory.owner_clan_id:
            ClanInfluenceService().recalculate(
                self.db,
                territory.owner_clan_id,
                action="territory_influence_admin_update",
                source_type="territory",
                source_id=territory.id,
            )
        
        self.db.commit()
        self.db.refresh(territory)
        return territory

    def delete(self, territory_id: int) -> bool:
        territory = self.get_by_id(territory_id)
        if not territory:
            return False
        
        self.db.delete(territory)
        self.db.commit()
        return True

    def add_attacking_clan(self, territory_id: int, clan_id: int) -> bool:
        # Проверяем, что территория существует
        territory = self.get_by_id(territory_id)
        if not territory:
            return False
        
        # Проверяем, что клан еще не атакует эту территорию
        existing = self.db.query(TerritoryAttackingClans).filter(
            and_(TerritoryAttackingClans.territory_id == territory_id,
                 TerritoryAttackingClans.clan_id == clan_id)
        ).first()
        
        if existing:
            return False
        
        # Добавляем атакующий клан
        attacking_clan = TerritoryAttackingClans(
            territory_id=territory_id,
            clan_id=clan_id
        )
        self.db.add(attacking_clan)
        
        # Обновляем статус территории
        territory.status = 'contested'
        
        self.db.commit()
        return True

    def add_defending_clan(self, territory_id: int, clan_id: int) -> bool:
        # Проверяем, что территория существует
        territory = self.get_by_id(territory_id)
        if not territory:
            return False
        
        # Проверяем, что клан еще не защищает эту территорию
        existing = self.db.query(TerritoryDefendingClans).filter(
            and_(TerritoryDefendingClans.territory_id == territory_id,
                 TerritoryDefendingClans.clan_id == clan_id)
        ).first()
        
        if existing:
            return False
        
        # Добавляем защищающий клан
        defending_clan = TerritoryDefendingClans(
            territory_id=territory_id,
            clan_id=clan_id
        )
        self.db.add(defending_clan)
        
        self.db.commit()
        return True

    def remove_clan_from_territory(self, territory_id: int, clan_id: int) -> bool:
        # Удаляем из атакующих кланов
        attacking = self.db.query(TerritoryAttackingClans).filter(
            and_(TerritoryAttackingClans.territory_id == territory_id,
                 TerritoryAttackingClans.clan_id == clan_id)
        ).first()
        if attacking:
            self.db.delete(attacking)
        
        # Удаляем из защищающих кланов
        defending = self.db.query(TerritoryDefendingClans).filter(
            and_(TerritoryDefendingClans.territory_id == territory_id,
                 TerritoryDefendingClans.clan_id == clan_id)
        ).first()
        if defending:
            self.db.delete(defending)
        
        # Проверяем, нужно ли изменить статус территории
        territory = self.get_by_id(territory_id)
        if territory:
            attacking_count = self.db.query(TerritoryAttackingClans).filter(
                TerritoryAttackingClans.territory_id == territory_id
            ).count()
            defending_count = self.db.query(TerritoryDefendingClans).filter(
                TerritoryDefendingClans.territory_id == territory_id
            ).count()
            
            if attacking_count == 0 and defending_count == 0:
                territory.status = 'neutral'
        
        self.db.commit()
        return True

    def get_territory_stats(self) -> dict:
        total = self.db.query(Territory).count()
        contested = self.db.query(Territory).filter(Territory.status == 'contested').count()
        neutral = self.db.query(Territory).filter(Territory.status == 'neutral').count()
        active = self.db.query(Territory).filter(Territory.status == 'active').count()
        
        return {
            'total': total,
            'contested': contested,
            'neutral': neutral,
            'active': active,
            'contested_percentage': round((contested / total * 100) if total > 0 else 0),
            'neutral_percentage': round((neutral / total * 100) if total > 0 else 0),
            'active_percentage': round((active / total * 100) if total > 0 else 0)
        }
