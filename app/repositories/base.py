from typing import Generic, TypeVar, Type, Optional, List, Any, Dict
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.database import Base

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    """Базовый репозиторий для работы с моделями"""
    
    def __init__(self, model: Type[ModelType]):
        self.model = model

    def _as_dict(self, obj_in: Any, *, exclude_unset: bool = False) -> Dict[str, Any]:
        if obj_in is None:
            return {}
        if isinstance(obj_in, dict):
            return obj_in
        if hasattr(obj_in, "model_dump"):
            return obj_in.model_dump(exclude_unset=exclude_unset)
        if hasattr(obj_in, "dict"):
            return obj_in.dict(exclude_unset=exclude_unset)
        return dict(obj_in)
    
    def get(self, db: Session, id: Any) -> Optional[ModelType]:
        """Получить объект по ID"""
        return db.query(self.model).filter(self.model.id == id).first()
    
    def get_multi(
        self, 
        db: Session, 
        *, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[ModelType]:
        """Получить список объектов с пагинацией"""
        return db.query(self.model).offset(skip).limit(limit).all()
    
    def create(self, db: Session, *, obj_in: Dict[str, Any]) -> ModelType:
        """Создать новый объект"""
        obj_data = self._as_dict(obj_in)
        db_obj = self.model(**obj_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(
        self,
        db: Session,
        *,
        db_obj: ModelType,
        obj_in: Dict[str, Any]
    ) -> ModelType:
        """Обновить объект"""
        update_data = self._as_dict(obj_in, exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def remove(self, db: Session, *, id: int) -> ModelType:
        """Удалить объект"""
        obj = db.query(self.model).get(id)
        db.delete(obj)
        db.commit()
        return obj
    
    def get_by_field(
        self, 
        db: Session, 
        field: str, 
        value: Any
    ) -> Optional[ModelType]:
        """Получить объект по полю"""
        return db.query(self.model).filter(getattr(self.model, field) == value).first()
    
    def get_by_fields(
        self, 
        db: Session, 
        filters: Dict[str, Any]
    ) -> List[ModelType]:
        """Получить объекты по нескольким полям"""
        query = db.query(self.model)
        for field, value in filters.items():
            query = query.filter(getattr(self.model, field) == value)
        return query.all() 
