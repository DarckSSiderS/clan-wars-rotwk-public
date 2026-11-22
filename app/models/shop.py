from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class ShopItem(Base):
    __tablename__ = "shop_items"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String)
    price = Column(Integer, nullable=False)
    item_type = Column(String, nullable=False)  # 'profile_frame', 'stat_card_style', etc.
    rarity = Column(String, default="common")  # common, rare, epic, legendary
    image_url = Column(String)
    css_class = Column(String)  # CSS класс для применения стилей
    slot = Column(String, nullable=True)
    category = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_available = Column(Boolean, default=True)  # Доступен ли предмет для покупки
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class UserItem(Base):
    __tablename__ = "user_items"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("shop_items.id"), nullable=False)
    is_equipped = Column(Boolean, default=False)
    purchased_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="items")
    item = relationship("ShopItem") 
