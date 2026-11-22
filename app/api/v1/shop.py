from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.core.auth import (
    get_current_active_user,
    get_current_admin_user,
    get_onboarded_active_user,
)
from app.services.shop_service import ShopItemService, UserItemService
from app.schemas.shop import (
    ShopItem, ShopItemCreate, ShopItemUpdate,
    UserItem, PurchaseRequest, EquipRequest, PurchaseResponse
)
from app.schemas.user import User

router = APIRouter(prefix="/shop", tags=["shop"])

# Предметы магазина
@router.get("/items/", response_model=List[ShopItem])
async def get_shop_items(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить список предметов магазина"""
    shop_service = ShopItemService()
    return shop_service.get_shop_items(db, skip=skip, limit=limit)

@router.get("/items/available/", response_model=List[ShopItem])
async def get_available_items(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить доступные предметы"""
    shop_service = ShopItemService()
    return shop_service.get_available_items(db)

@router.get("/items/category/{category}", response_model=List[ShopItem])
async def get_items_by_category(
    category: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить предметы по категории"""
    shop_service = ShopItemService()
    return shop_service.get_items_by_category(db, category)

@router.get("/items/type/{item_type}", response_model=List[ShopItem])
async def get_items_by_type(
    item_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить предметы по типу"""
    shop_service = ShopItemService()
    return shop_service.get_items_by_type(db, item_type)

@router.get("/items/{item_id:int}", response_model=ShopItem)
async def get_shop_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить предмет магазина по ID"""
    shop_service = ShopItemService()
    return shop_service.get_shop_item(db, item_id)

@router.post("/items/", response_model=ShopItem)
async def create_shop_item(
    item_data: ShopItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Создать новый предмет магазина"""
    shop_service = ShopItemService()
    return shop_service.create_shop_item(db, item_data)

@router.put("/items/{item_id:int}", response_model=ShopItem)
async def update_shop_item(
    item_id: int,
    item_data: ShopItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Обновить предмет магазина"""
    shop_service = ShopItemService()
    return shop_service.update_shop_item(db, item_id, item_data)

@router.delete("/items/{item_id:int}")
async def delete_shop_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Удалить предмет магазина"""
    shop_service = ShopItemService()
    shop_service.delete_shop_item(db, item_id)
    return {"message": "Предмет удален"}

# Предметы пользователей
@router.get("/my-items/", response_model=List[UserItem])
async def get_my_items(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить предметы текущего пользователя"""
    user_item_service = UserItemService()
    return user_item_service.get_user_items(db, current_user.id)

@router.get("/my-items/equipped/", response_model=List[UserItem])
async def get_my_equipped_items(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить экипированные предметы текущего пользователя"""
    user_item_service = UserItemService()
    return user_item_service.get_equipped_items(db, current_user.id)

@router.get("/users/{user_id:int}/items/", response_model=List[UserItem])
async def get_user_items(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить предметы пользователя"""
    user_item_service = UserItemService()
    return user_item_service.get_user_items(db, user_id)

@router.get("/users/{user_id:int}/items/equipped/", response_model=List[UserItem])
async def get_user_equipped_items(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Получить экипированные предметы пользователя"""
    user_item_service = UserItemService()
    return user_item_service.get_equipped_items(db, user_id)

# Покупка и экипировка
@router.post("/purchase/", response_model=PurchaseResponse)
async def purchase_item(
    purchase_data: PurchaseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_onboarded_active_user)
):
    """Купить предмет"""
    user_item_service = UserItemService()
    return user_item_service.purchase_item(db, current_user.id, purchase_data)

@router.post("/equip/", response_model=UserItem)
async def equip_item(
    equip_data: EquipRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_onboarded_active_user)
):
    """Экипировать предмет"""
    user_item_service = UserItemService()
    return user_item_service.equip_item(db, current_user.id, equip_data)

@router.post("/unequip/{user_item_id:int}", response_model=UserItem)
async def unequip_item(
    user_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_onboarded_active_user)
):
    """Снять предмет"""
    user_item_service = UserItemService()
    return user_item_service.unequip_item(db, current_user.id, user_item_id) 
