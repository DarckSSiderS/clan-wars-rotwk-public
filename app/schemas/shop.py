from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class ShopItemBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: int
    item_type: str
    rarity: str = "common"
    image_url: Optional[str] = None
    css_class: Optional[str] = None
    slot: Optional[str] = None
    category: Optional[str] = None
    is_available: bool = True

class ShopItemCreate(ShopItemBase):
    pass

class ShopItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = None
    item_type: Optional[str] = None
    rarity: Optional[str] = None
    image_url: Optional[str] = None
    css_class: Optional[str] = None
    slot: Optional[str] = None
    category: Optional[str] = None
    is_available: Optional[bool] = None

class ShopItem(ShopItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime

class UserItemBase(BaseModel):
    is_equipped: bool = False

class UserItem(UserItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    item_id: int
    purchased_at: datetime
    item: ShopItem

class PurchaseRequest(BaseModel):
    item_id: int

class EquipRequest(BaseModel):
    user_item_id: int

class PurchaseResponse(BaseModel):
    user_item: UserItem
    new_balance: int
    item_price: int 
