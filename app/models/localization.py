from sqlalchemy import Column, Integer, String, Text
from app.database import Base

class Localization(Base):
    __tablename__ = "localizations"

    id = Column(Integer, primary_key=True, index=True)
    identifier = Column(String(255), unique=True, index=True, nullable=False)  # Уникальный идентификатор
    ru = Column(Text, nullable=False)  # Русский перевод
    eng = Column(Text, nullable=False)  # Английский перевод
    webpage = Column(String(100), nullable=False)  # На какой странице используется 