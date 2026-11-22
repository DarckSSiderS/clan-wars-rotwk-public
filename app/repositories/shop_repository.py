from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.shop import ShopItem, UserItem
from app.repositories.base import BaseRepository


class ShopItemRepository(BaseRepository[ShopItem]):
    """Репозиторий для работы с предметами магазина"""
    
    def __init__(self):
        super().__init__(ShopItem)
    
    def get_available_items(self, db: Session) -> List[ShopItem]:
        """Получить все доступные предметы"""
        return db.query(ShopItem).filter(ShopItem.is_available == True).all()
    
    def get_items_by_category(self, db: Session, category: str) -> List[ShopItem]:
        """Получить предметы по категории"""
        return db.query(ShopItem).filter(ShopItem.category == category).all()
    
    def get_items_by_type(self, db: Session, item_type: str) -> List[ShopItem]:
        """Получить предметы по типу"""
        return db.query(ShopItem).filter(ShopItem.item_type == item_type).all()


class UserItemRepository(BaseRepository[UserItem]):
    """Репозиторий для работы с предметами пользователей"""
    
    def __init__(self):
        super().__init__(UserItem)
    
    def get_user_items(self, db: Session, user_id: int) -> List[UserItem]:
        """Получить все предметы пользователя"""
        return db.query(UserItem).filter(UserItem.user_id == user_id).all()
    
    def get_user_item_by_shop_item(self, db: Session, user_id: int, shop_item_id: int) -> Optional[UserItem]:
        """Получить предмет пользователя по предмету магазина"""
        return db.query(UserItem).filter(
            and_(
                UserItem.user_id == user_id,
                UserItem.item_id == shop_item_id
            )
        ).first()
    
    def get_equipped_items(self, db: Session, user_id: int) -> List[UserItem]:
        """Получить экипированные предметы пользователя"""
        return db.query(UserItem).filter(
            and_(
                UserItem.user_id == user_id,
                UserItem.is_equipped == True
            )
        ).all()

    def unequip_slot(
        self,
        db: Session,
        user_id: int,
        slot: str,
        *,
        except_user_item_id: Optional[int] = None,
    ) -> None:
        """Снять другие предметы из эксклюзивного слота."""
        query = (
            db.query(UserItem)
            .join(ShopItem, ShopItem.id == UserItem.item_id)
            .filter(
                UserItem.user_id == user_id,
                UserItem.is_equipped == True,
                ShopItem.slot == slot,
            )
        )
        if except_user_item_id is not None:
            query = query.filter(UserItem.id != except_user_item_id)
        for equipped_item in query.all():
            equipped_item.is_equipped = False
