from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.user import User
from app.repositories.base import BaseRepository
from app.core.security import get_password_hash

class UserRepository(BaseRepository[User]):
    def __init__(self):
        super().__init__(User)
    
    def get_by_username(self, db: Session, username: str) -> Optional[User]:
        """Получить пользователя по имени пользователя"""
        return self.get_by_field(db, "username", username)

    def get_by_username_case_insensitive(self, db: Session, username: str) -> Optional[User]:
        return db.query(User).filter(func.lower(User.username) == username.lower()).first()
    
    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        """Получить пользователя по email"""
        return self.get_by_field(db, "email", email)

    def get_by_email_case_insensitive(self, db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(func.lower(User.email) == email.lower()).first()
    
    def create_user(self, db: Session, username: str, email: str, password: str, language: str = "ru", allow_clan_invites: bool = True, telegram_url: str = None, twitch_url: str = None, youtube_url: str = None, is_claimed: bool = True) -> User:
        """Создать нового пользователя"""
        hashed_password = get_password_hash(password)
        user_data = {
            "username": username,
            "email": email,
            "hashed_password": hashed_password,
            "is_claimed": is_claimed,
            "language": language,
            "allow_clan_invites": allow_clan_invites,
            "telegram_url": telegram_url,
            "twitch_url": twitch_url,
            "youtube_url": youtube_url
        }
        return self.create(db, obj_in=user_data)

    def create_ladder_profile(self, db: Session, username: str, email: str) -> User:
        return self.create(db, obj_in={
            "username": username,
            "email": email,
            "hashed_password": "!",
            "is_active": True,
            "is_claimed": False,
            "language": "ru",
            "allow_clan_invites": False,
        })

    def claim_ladder_profile(self, db: Session, user: User, *, email: str, password: str,
                             language: str, allow_clan_invites: bool, telegram_url: str = None,
                             twitch_url: str = None, youtube_url: str = None) -> User:
        user.email = email
        user.hashed_password = get_password_hash(password)
        user.language = language
        user.allow_clan_invites = allow_clan_invites
        user.telegram_url = telegram_url
        user.twitch_url = twitch_url
        user.youtube_url = youtube_url
        user.is_claimed = True
        db.commit()
        db.refresh(user)
        return user
    
    def update_balance(self, db: Session, user_id: int, amount: int) -> Optional[User]:
        """Обновить баланс пользователя"""
        user = self.get(db, user_id)
        if user:
            user.balance += amount
            db.commit()
            db.refresh(user)
        return user
    
    def update_avatar(self, db: Session, user_id: int, avatar_url: str) -> Optional[User]:
        """Обновить аватар пользователя"""
        user = self.get(db, user_id)
        if user:
            user.avatar_url = avatar_url
            db.commit()
            db.refresh(user)
        return user
    
    def get_user_statistics(self, db: Session, username: str) -> Optional[dict]:
        """Получить статистику пользователя"""
        from app.models.match import Match

        from app.services.user_service import UserService
        from app.services.player_match_scope import PlayerMatchScope
        user = UserService().get_public_profile(db, username)
        if user is not None:
            scope = PlayerMatchScope(db, user)
            matches = scope.query(db).all()
            wins = sum(scope.is_winner(match) for match in matches)
            total = len(matches)
            return {
                "player": user.display_name or user.username,
                "wins": wins, "losses": total - wins,
                "total_matches": total,
                "win_rate": round(wins * 100 / total, 2) if total else 0,
            }
        
        # Подсчитываем победы
        wins = db.query(func.count(Match.id)).filter(
            Match.winner_player == username
        ).scalar()
        
        # Подсчитываем поражения
        losses = db.query(func.count(Match.id)).filter(
            Match.loser_player == username
        ).scalar()
        
        total_matches = wins + losses
        win_rate = (wins / total_matches * 100) if total_matches > 0 else 0
        
        return {
            "player": username,
            "wins": wins,
            "losses": losses,
            "total_matches": total_matches,
            "win_rate": round(win_rate, 2)
        }

    def search_by_username(self, db: Session, username: str, skip: int = 0, limit: int = 10) -> List[User]:
        """Поиск пользователей по имени"""
        return db.query(User).filter(
            User.username.ilike(f"%{username}%"),
            User.is_claimed.is_(True),
        ).offset(skip).limit(limit).all() 
