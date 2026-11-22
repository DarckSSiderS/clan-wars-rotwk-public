from typing import List, Optional
from sqlalchemy.orm import Session

from app.repositories.shop_repository import ShopItemRepository, UserItemRepository
from app.repositories.user_repository import UserRepository
from app.core.exceptions import (
    ItemNotFoundException, UserNotFoundException,
    InsufficientFundsException, ItemAlreadyOwnedException, ItemUnavailableException
)
from app.schemas.shop import ShopItemCreate, ShopItemUpdate, PurchaseRequest, EquipRequest
from app.services.notification_service import notification_service


class ShopItemService:
    """Сервис для работы с предметами магазина"""
    
    def __init__(self):
        self.shop_item_repo = ShopItemRepository()
    
    def get_shop_item(self, db: Session, item_id: int):
        """Получить предмет магазина по ID"""
        item = self.shop_item_repo.get(db, item_id)
        if not item:
            raise ItemNotFoundException(item_id)
        return item
    
    def get_shop_items(self, db: Session, skip: int = 0, limit: int = 100) -> List:
        """Получить список предметов магазина"""
        return self.shop_item_repo.get_multi(db, skip=skip, limit=limit)
    
    def get_available_items(self, db: Session) -> List:
        """Получить доступные предметы"""
        return self.shop_item_repo.get_available_items(db)
    
    def get_items_by_category(self, db: Session, category: str) -> List:
        """Получить предметы по категории"""
        return self.shop_item_repo.get_items_by_category(db, category)
    
    def get_items_by_type(self, db: Session, item_type: str) -> List:
        """Получить предметы по типу"""
        return self.shop_item_repo.get_items_by_type(db, item_type)
    
    def create_shop_item(self, db: Session, item_data: ShopItemCreate):
        """Создать новый предмет магазина"""
        return self.shop_item_repo.create(db, obj_in=item_data)
    
    def update_shop_item(self, db: Session, item_id: int, item_data: ShopItemUpdate):
        """Обновить предмет магазина"""
        item = self.get_shop_item(db, item_id)
        return self.shop_item_repo.update(db, db_obj=item, obj_in=item_data)
    
    def delete_shop_item(self, db: Session, item_id: int):
        """Удалить предмет магазина"""
        item = self.get_shop_item(db, item_id)
        return self.shop_item_repo.remove(db, id=item_id)


class UserItemService:
    """Сервис для работы с предметами пользователей"""
    
    def __init__(self):
        self.user_item_repo = UserItemRepository()
        self.shop_item_repo = ShopItemRepository()
        self.user_repo = UserRepository()
    
    def get_user_items(self, db: Session, user_id: int) -> List:
        """Получить все предметы пользователя"""
        return self.user_item_repo.get_user_items(db, user_id)
    
    def get_equipped_items(self, db: Session, user_id: int) -> List:
        """Получить экипированные предметы пользователя"""
        return self.user_item_repo.get_equipped_items(db, user_id)
    
    def purchase_item(self, db: Session, user_id: int, purchase_data: PurchaseRequest):
        """Купить предмет"""
        # Проверяем существование пользователя
        user = self.user_repo.get(db, user_id)
        if not user:
            raise UserNotFoundException(user_id=user_id)
        
        # Проверяем существование предмета
        shop_item = self.shop_item_repo.get(db, purchase_data.item_id)
        if not shop_item:
            raise ItemNotFoundException(purchase_data.item_id)
        if not shop_item.is_available:
            raise ItemUnavailableException()
        
        # Проверяем, не куплен ли уже предмет
        existing_item = self.user_item_repo.get_user_item_by_shop_item(db, user_id, purchase_data.item_id)
        if existing_item:
            raise ItemAlreadyOwnedException()
        
        # Проверяем достаточно ли средств
        if user.balance < shop_item.price:
            raise InsufficientFundsException(shop_item.price, user.balance)
        
        # Создаем предмет пользователя
        user_item_data = {
            "user_id": user_id,
            "item_id": purchase_data.item_id,
            "is_equipped": False
        }
        user_item = self.user_item_repo.create(db, obj_in=user_item_data)
        
        # Списываем средства
        user.balance -= shop_item.price
        notification_service.create(
            db,
            user_id=user_id,
            notification_type="shop_purchase",
            title="Реликвия добавлена в коллекцию",
            message=f"Вы приобрели «{shop_item.name}» за {shop_item.price} монет.",
            link_url="/shop",
            entity_type="shop_item",
            entity_id=shop_item.id,
            commit=False,
        )
        db.commit()
        db.refresh(user)
        
        # Возвращаем информацию о покупке
        return {
            "user_item": user_item,
            "new_balance": user.balance,
            "item_price": shop_item.price
        }
    
    def equip_item(self, db: Session, user_id: int, equip_data: EquipRequest):
        """Экипировать предмет"""
        # Проверяем существование пользователя
        user = self.user_repo.get(db, user_id)
        if not user:
            raise UserNotFoundException(user_id=user_id)
        
        # Получаем предмет пользователя
        user_item = self.user_item_repo.get(db, equip_data.user_item_id)
        if not user_item or user_item.user_id != user_id:
            raise ItemNotFoundException(equip_data.user_item_id)
        
        # Получаем информацию о предмете
        shop_item = self.shop_item_repo.get(db, user_item.item_id)
        if not shop_item:
            raise ItemNotFoundException(user_item.item_id)

        # Один слот представляет один визуальный выбор. Например, две темы
        # сайта не должны оставаться активными одновременно.
        if shop_item.slot:
            self.user_item_repo.unequip_slot(
                db,
                user_id,
                shop_item.slot,
                except_user_item_id=user_item.id,
            )
        
        # Экипируем предмет
        user_item.is_equipped = True
        db.commit()
        db.refresh(user_item)
        
        return user_item
    
    def unequip_item(self, db: Session, user_id: int, user_item_id: int):
        """Снять предмет"""
        # Проверяем существование пользователя
        user = self.user_repo.get(db, user_id)
        if not user:
            raise UserNotFoundException(user_id=user_id)
        
        # Получаем предмет пользователя
        user_item = self.user_item_repo.get(db, user_item_id)
        if not user_item or user_item.user_id != user_id:
            raise ItemNotFoundException(user_item_id)
        
        # Снимаем предмет
        user_item.is_equipped = False
        db.commit()
        db.refresh(user_item)
        
        return user_item 
