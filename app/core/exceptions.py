from fastapi import HTTPException, status
from typing import Any, Dict, Optional

class ClanWarException(HTTPException):
    """Базовое исключение для ClanWar приложения"""
    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)

class UserNotFoundException(ClanWarException):
    """Пользователь не найден"""
    def __init__(self, user_id: Optional[int] = None, username: Optional[str] = None):
        detail = "Пользователь не найден"
        if user_id:
            detail = f"Пользователь с ID {user_id} не найден"
        elif username:
            detail = f"Пользователь '{username}' не найден"
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class ClanNotFoundException(ClanWarException):
    """Клан не найден"""
    def __init__(self, clan_id: Optional[int] = None, clan_name: Optional[str] = None):
        detail = "Клан не найден"
        if clan_id:
            detail = f"Клан с ID {clan_id} не найден"
        elif clan_name:
            detail = f"Клан '{clan_name}' не найден"
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class InsufficientPermissionsException(ClanWarException):
    """Недостаточно прав"""
    def __init__(self, action: str = "выполнить это действие"):
        detail = f"Недостаточно прав для {action}"
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

class UserAlreadyInClanException(ClanWarException):
    """Пользователь уже состоит в клане"""
    def __init__(self):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail="Пользователь уже состоит в клане")

class RegistrationConflictException(ClanWarException):
    """Ник или email уже нельзя использовать для регистрации."""
    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)

class ClanNameAlreadyExistsException(ClanWarException):
    """Название клана уже существует"""
    def __init__(self, clan_name: str):
        detail = f"Клан с названием '{clan_name}' уже существует"
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

class InsufficientFundsException(ClanWarException):
    """Недостаточно средств"""
    def __init__(self, required: int, available: int):
        detail = f"Недостаточно средств. Требуется: {required}, доступно: {available}"
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

class ItemNotFoundException(ClanWarException):
    """Предмет не найден"""
    def __init__(self, item_id: int):
        detail = f"Предмет с ID {item_id} не найден"
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class ItemAlreadyOwnedException(ClanWarException):
    """Предмет уже куплен"""
    def __init__(self):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail="Предмет уже куплен")

class ItemUnavailableException(ClanWarException):
    """Предмет недоступен для покупки"""
    def __init__(self):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail="Предмет недоступен для покупки")

class WarNotFoundException(ClanWarException):
    """Война не найдена"""
    def __init__(self, war_id: int):
        detail = f"Война с ID {war_id} не найдена"
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class TerritoryNotFoundException(ClanWarException):
    """Территория не найдена"""
    def __init__(self, territory_id: int):
        detail = f"Территория с ID {territory_id} не найдена"
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class ClanWarNotFoundException(ClanWarException):
    """Клановая война не найдена"""
    def __init__(self, war_id: int):
        detail = f"Клановая война с ID {war_id} не найдена"
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class WarCreationException(ClanWarException):
    """Structured conflict/validation response for the deployment workflow."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = status.HTTP_409_CONFLICT,
        user_ids: Optional[list[int]] = None,
    ):
        detail: Dict[str, Any] = {"code": code, "message": message}
        if user_ids:
            detail["user_ids"] = user_ids
        super().__init__(status_code=status_code, detail=detail)

class AchievementNotFoundException(ClanWarException):
    """Достижение не найдено"""
    def __init__(self, achievement_id: int):
        detail = f"Достижение с ID {achievement_id} не найдено"
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class UserAchievementNotFoundException(ClanWarException):
    """Достижение пользователя не найдено"""
    def __init__(self, user_id: int, achievement_id: int):
        detail = f"Достижение пользователя {user_id} с ID {achievement_id} не найдено"
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail) 
