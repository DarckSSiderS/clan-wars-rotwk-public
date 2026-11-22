from app.repositories.localization_repository import LocalizationRepository
from app.schemas.localization import LocalizationCreate, Localization
from sqlalchemy.orm import Session
from typing import List, Optional, Dict

class LocalizationService:
    def __init__(self):
        pass

    def get_all_localizations(self, db: Session) -> List[Localization]:
        """Получить все записи локализации"""
        repo = LocalizationRepository(db)
        return repo.get_all()

    def get_localization_by_identifier(self, db: Session, identifier: str) -> Optional[Localization]:
        """Получить запись локализации по идентификатору"""
        repo = LocalizationRepository(db)
        return repo.get_by_identifier(identifier)

    def get_localizations_by_webpage(self, db: Session, webpage: str) -> List[Localization]:
        """Получить все записи локализации для определенной страницы"""
        repo = LocalizationRepository(db)
        return repo.get_by_webpage(webpage)

    def get_text(self, db: Session, identifier: str, language: str = "ru") -> Optional[str]:
        """Получить текст по идентификатору и языку"""
        repo = LocalizationRepository(db)
        return repo.get_text(identifier, language)

    def get_webpage_texts(self, db: Session, webpage: str, language: str = "ru") -> Dict[str, str]:
        """Получить все тексты для страницы в виде словаря {identifier: text}"""
        repo = LocalizationRepository(db)
        localizations = repo.get_by_webpage(webpage)
        result = {}
        for loc in localizations:
            if language == "eng":
                result[loc.identifier] = loc.eng
            else:
                result[loc.identifier] = loc.ru
        return result

    def create_localization(self, db: Session, localization: LocalizationCreate) -> Localization:
        """Создать новую запись локализации"""
        repo = LocalizationRepository(db)
        return repo.create(
            identifier=localization.identifier,
            ru=localization.ru,
            eng=localization.eng,
            webpage=localization.webpage
        )

    def update_localization(self, db: Session, identifier: str, ru: str = None, eng: str = None, webpage: str = None) -> Optional[Localization]:
        """Обновить запись локализации"""
        repo = LocalizationRepository(db)
        return repo.update(identifier, ru, eng, webpage)

    def delete_localization(self, db: Session, identifier: str) -> bool:
        """Удалить запись локализации"""
        repo = LocalizationRepository(db)
        return repo.delete(identifier) 