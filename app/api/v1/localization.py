from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict
from app.database import get_db
from app.schemas.localization import Localization, LocalizationCreate
from app.services.localization_service import LocalizationService
from app.core.auth import get_current_admin_user
from app.models.user import User

router = APIRouter()

@router.get("/", response_model=List[Localization])
async def get_all_localizations(db: Session = Depends(get_db)):
    """Получить все записи локализации"""
    service = LocalizationService()
    return service.get_all_localizations(db)

@router.get("/webpage/{webpage}", response_model=List[Localization])
async def get_localizations_by_webpage(webpage: str, db: Session = Depends(get_db)):
    """Получить все записи локализации для определенной страницы"""
    service = LocalizationService()
    return service.get_localizations_by_webpage(db, webpage)

@router.get("/text/{identifier}")
async def get_text(identifier: str, language: str = "ru", db: Session = Depends(get_db)):
    """Получить текст по идентификатору и языку"""
    service = LocalizationService()
    text = service.get_text(db, identifier, language)
    if text is None:
        raise HTTPException(status_code=404, detail="Text not found")
    return {"identifier": identifier, "language": language, "text": text}

@router.get("/webpage/{webpage}/texts")
async def get_webpage_texts(webpage: str, language: str = "ru", db: Session = Depends(get_db)):
    """Получить все тексты для страницы в виде словаря"""
    service = LocalizationService()
    texts = service.get_webpage_texts(db, webpage, language)
    return {"webpage": webpage, "language": language, "texts": texts}

@router.post("/", response_model=Localization)
async def create_localization(
    localization: LocalizationCreate,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Создать новую запись локализации"""
    service = LocalizationService()
    return service.create_localization(db, localization)

@router.put("/{identifier}", response_model=Localization)
async def update_localization(
    identifier: str, 
    ru: str = None, 
    eng: str = None, 
    webpage: str = None, 
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Обновить запись локализации"""
    service = LocalizationService()
    localization = service.update_localization(db, identifier, ru, eng, webpage)
    if localization is None:
        raise HTTPException(status_code=404, detail="Localization not found")
    return localization

@router.delete("/{identifier}")
async def delete_localization(
    identifier: str,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Удалить запись локализации"""
    service = LocalizationService()
    success = service.delete_localization(db, identifier)
    if not success:
        raise HTTPException(status_code=404, detail="Localization not found")
    return {"message": "Localization deleted successfully"} 
