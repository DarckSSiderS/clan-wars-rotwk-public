from sqlalchemy.orm import Session
from app.models.localization import Localization
from typing import List, Optional

class LocalizationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> List[Localization]:
        """Получить все записи локализации"""
        return self.db.query(Localization).all()

    def get_by_identifier(self, identifier: str) -> Optional[Localization]:
        """Получить запись по идентификатору"""
        return self.db.query(Localization).filter(Localization.identifier == identifier).first()

    def get_by_webpage(self, webpage: str) -> List[Localization]:
        """Получить все записи для определенной страницы"""
        return self.db.query(Localization).filter(Localization.webpage == webpage).all()

    def get_text(self, identifier: str, language: str = "ru") -> Optional[str]:
        """Получить текст по идентификатору и языку"""
        loc = self.get_by_identifier(identifier)
        if loc:
            if language == "eng":
                return loc.eng
            else:
                return loc.ru
        return None

    def create(self, identifier: str, ru: str, eng: str, webpage: str) -> Localization:
        """Создать новую запись локализации"""
        localization = Localization(
            identifier=identifier,
            ru=ru,
            eng=eng,
            webpage=webpage
        )
        self.db.add(localization)
        self.db.commit()
        self.db.refresh(localization)
        return localization

    def update(self, identifier: str, ru: str = None, eng: str = None, webpage: str = None) -> Optional[Localization]:
        """Обновить запись локализации"""
        loc = self.get_by_identifier(identifier)
        if loc:
            if ru is not None:
                loc.ru = ru
            if eng is not None:
                loc.eng = eng
            if webpage is not None:
                loc.webpage = webpage
            self.db.commit()
            self.db.refresh(loc)
        return loc

    def delete(self, identifier: str) -> bool:
        """Удалить запись локализации"""
        loc = self.get_by_identifier(identifier)
        if loc:
            self.db.delete(loc)
            self.db.commit()
            return True
        return False 