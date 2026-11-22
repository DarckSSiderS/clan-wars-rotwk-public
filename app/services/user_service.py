from typing import Optional, List
from uuid import uuid4
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.repositories.user_repository import UserRepository
from app.models.user import User
from app.models.match import Match, MatchParticipant
from app.schemas.user import UserCreate, UserUpdate
from app.core.exceptions import UserNotFoundException, RegistrationConflictException

class UserService:
    def __init__(self):
        self.repository = UserRepository()
    
    def get_user(self, db: Session, user_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        return self.repository.get(db, user_id)
    
    def get_user_by_username(self, db: Session, username: str) -> Optional[User]:
        """Получить пользователя по имени пользователя"""
        return self.repository.get_by_username(db, username)
    
    def get_users(self, db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        """Получить список пользователей"""
        return self.repository.get_multi(db, skip=skip, limit=limit)
    
    def create_user(self, db: Session, user: UserCreate) -> User:
        """Создать нового пользователя"""
        username = user.username.strip()
        existing_user = self.repository.get_by_username(db, username)
        if existing_user:
            if existing_user.is_claimed:
                raise RegistrationConflictException(f"Ник '{username}' уже зарегистрирован")
            if not user.claim_existing_profile:
                raise RegistrationConflictException(
                    "Для этого ника уже сохранены матчи и достижения. Подтвердите привязку игрового профиля."
                )
            existing_email = self.repository.get_by_email_case_insensitive(db, user.email)
            if existing_email and existing_email.id != existing_user.id:
                raise RegistrationConflictException("Этот email уже используется")
            from app.services.achievement_service import UserAchievementService
            UserAchievementService().get_user_achievements(db, existing_user.id)
            claimed_user = self.repository.claim_ladder_profile(
                db,
                existing_user,
                email=user.email,
                password=user.password,
                language=user.language,
                allow_clan_invites=user.allow_clan_invites,
                telegram_url=user.telegram_url,
                twitch_url=user.twitch_url,
                youtube_url=user.youtube_url,
            )
            from app.services.external_identity_service import ExternalIdentityService
            ExternalIdentityService().mark_claimed(db, claimed_user)
            return claimed_user

        similar_user = self.repository.get_by_username_case_insensitive(db, username)
        if similar_user:
            if similar_user.is_claimed:
                raise RegistrationConflictException(f"Ник '{similar_user.username}' уже зарегистрирован")
            raise RegistrationConflictException(
                f"Для привязки профиля введите ник точно с тем же регистром: {similar_user.username}"
            )

        existing_email = self.repository.get_by_email_case_insensitive(db, user.email)
        if existing_email:
            raise RegistrationConflictException("Этот email уже используется")
        
        return self.repository.create_user(
            db, 
            username=username,
            email=user.email, 
            password=user.password,
            language=user.language,
            allow_clan_invites=user.allow_clan_invites,
            telegram_url=user.telegram_url,
            twitch_url=user.twitch_url,
            youtube_url=user.youtube_url
        )

    def ensure_ladder_profile(
        self,
        db: Session,
        username: str,
        external_uuid: str = None,
    ) -> Optional[User]:
        """Создать публичный профиль для ника, который присутствует в импортированных матчах."""
        username = str(username or "").strip()
        if not username or username.lower().startswith("player_"):
            return None

        from app.services.external_identity_service import ExternalIdentityService
        identity_service = ExternalIdentityService()
        if external_uuid:
            identity = identity_service.get_by_uuid(db, external_uuid)
            if identity:
                identity_service.observe(db, identity.user, external_uuid, username)
                return identity.user
        else:
            identity = identity_service.get_by_nickname(db, username)
            if identity:
                from app.services.profile_reconciliation_service import ProfileReconciliationService
                ProfileReconciliationService().reconcile(db, identity)
                db.commit()
                return identity.user

        existing = self.repository.get_by_username(db, username)
        if existing:
            if external_uuid:
                identity_service.observe(db, existing, external_uuid, username)
            return existing
        existing = self.repository.get_by_username_case_insensitive(db, username)
        if existing:
            if external_uuid:
                identity_service.observe(db, existing, external_uuid, username)
            return existing

        has_matches = db.query(Match.id).filter(
            (Match.winner_player == username)
            | (Match.loser_player == username)
            | Match.participants.any(MatchParticipant.nickname == username)
        ).first()
        if not has_matches:
            return None

        synthetic_email = f"ladder-{uuid4().hex}@profiles.invalid"
        profile = self.repository.create_ladder_profile(db, username, synthetic_email)
        if external_uuid:
            identity_service.observe(db, profile, external_uuid, username)
        return profile

    def ensure_ladder_profiles(self, db: Session) -> int:
        """Backfill profiles for every distinct nickname already stored in match history."""
        usernames = {
            row[0].strip()
            for row in db.query(Match.winner_player).distinct().all()
            if row[0] and row[0].strip()
        }
        usernames.update({
            row[0].strip()
            for row in db.query(Match.loser_player).distinct().all()
            if row[0] and row[0].strip()
        })
        usernames.update({
            row[0].strip()
            for row in db.query(MatchParticipant.nickname).distinct().all()
            if row[0] and row[0].strip()
        })
        created = 0
        from app.services.external_identity_service import ExternalIdentityService
        identity_service = ExternalIdentityService()
        for username in usernames:
            if self.repository.get_by_username_case_insensitive(db, username):
                continue
            if identity_service.get_by_nickname(db, username):
                continue
            if self.ensure_ladder_profile(db, username):
                created += 1
        return created

    def get_public_profile(self, db: Session, username: str) -> Optional[User]:
        from app.services.external_identity_service import ExternalIdentityService
        identity = ExternalIdentityService().get_by_uuid(db, username)
        if identity:
            return identity.user
        identity = ExternalIdentityService().get_by_nickname(db, username)
        if identity:
            return identity.user
        user = self.repository.get_by_username(db, username)
        if user:
            return user
        display_user = (
            db.query(User)
            .filter(func.lower(User.display_name) == str(username or "").strip().lower())
            .order_by(User.is_claimed.desc(), User.id.asc())
            .first()
        )
        return display_user

    def get_or_create_public_profile(self, db: Session, username: str) -> Optional[User]:
        return self.get_public_profile(db, username) or self.ensure_ladder_profile(db, username)

    def get_registration_status(self, db: Session, username: str) -> dict:
        username = str(username or "").strip()
        if not username:
            return {"username": "", "status": "invalid"}

        user = self.get_or_create_public_profile(db, username)
        if not user:
            similar_user = self.repository.get_by_username_case_insensitive(db, username)
            if similar_user:
                return {
                    "username": username,
                    "exact_username": similar_user.username,
                    "status": "taken" if similar_user.is_claimed else "spelling_mismatch",
                }
            return {"username": username, "status": "available"}

        if user.username != username:
            return {
                "username": username,
                "exact_username": user.username,
                "status": "taken" if user.is_claimed else "spelling_mismatch",
            }
        if user.is_claimed:
            return {"username": username, "status": "taken"}

        from app.services.achievement_service import UserAchievementService
        achievements = UserAchievementService().get_user_achievements(db, user.id)
        statistics = self.get_user_statistics(db, username) or {}
        return {
            "username": username,
            "status": "claimable",
            "statistics": statistics,
            "completed_achievements": sum(1 for item in achievements if item.is_completed),
            "level": user.level,
            "external_identity_status": user.external_identity_status,
        }
    
    def update_user(self, db: Session, user_id: int, user_update: UserUpdate) -> Optional[User]:
        """Обновить пользователя"""
        user = self.get_user(db, user_id)
        if not user:
            raise UserNotFoundException(user_id=user_id)
        
        update_data = user_update.model_dump(exclude_unset=True)
        return self.repository.update(db, db_obj=user, obj_in=update_data)
    
    def update_balance(self, db: Session, user_id: int, amount: int) -> Optional[User]:
        """Обновить баланс пользователя"""
        user = self.get_user(db, user_id)
        if not user:
            raise UserNotFoundException(user_id=user_id)
        
        return self.repository.update_balance(db, user_id, amount)
    
    def update_avatar(self, db: Session, user_id: int, avatar_url: str) -> Optional[User]:
        """Обновить аватар пользователя"""
        user = self.get_user(db, user_id)
        if not user:
            raise UserNotFoundException(user_id=user_id)
        
        return self.repository.update_avatar(db, user_id, avatar_url)
    
    def get_user_statistics(self, db: Session, username: str) -> Optional[dict]:
        """Получить статистику пользователя"""
        return self.repository.get_user_statistics(db, username)

    def search_users_by_username(self, db: Session, username: str, skip: int = 0, limit: int = 10) -> List[User]:
        """Поиск пользователей по имени"""
        return self.repository.search_by_username(db, username, skip=skip, limit=limit) 
