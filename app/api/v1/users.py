from typing import List, Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    Query,
    status,
)
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func, or_
from app.database import get_db
from app.core.auth import (
    get_current_active_user,
    get_current_admin_user,
    get_current_session,
    get_current_user,
)
from app.core.session_cookie import set_session_cookie
from app.core.time import as_utc
from app.models.user import User as UserModel
from app.models.role import Role
from app.models.title import UserTitle
from app.models.external_identity import ExternalPlayerAlias, ExternalPlayerIdentity
from app.models.match import Match, MatchParticipant
from app.models.clan import Clan
from app.schemas.user import (
    User,
    PublicUser,
    UserUpdate,
    BalanceUpdate,
    IdentityVerificationReview,
    TerritoryContributionResponse,
)
from app.schemas.oauth import SessionUserSummary
from app.services.user_service import UserService
from app.services.achievement_service import UserAchievementService
from app.services.clan_experience_service import ClanExperienceService
from app.services.operation_service import AdminAuditService
from app.services.map_preview_storage_service import MapPreviewStorageService
from app.services.external_identity_service import ExternalIdentityService
from app.services.player_match_scope import PlayerMatchScope
from app.services.arena_current_rating_service import arena_current_ratings
from app.services.elo_service import is_unverified_rating
from app.services.territory_contribution_service import TerritoryContributionService
from app.services.session_service import InvalidSession, SessionService
from app.models.auth_session import UserSession
from app.repositories.user_repository import UserRepository
from app.utils.image_processor import process_avatar_image
from app.config import settings
import os
import uuid

router = APIRouter(prefix="/users", tags=["users"])
map_preview_storage = MapPreviewStorageService()


def _resolved_player_names(db: Session, requested_name: str) -> tuple[set[str], set[str]]:
    clean_name = requested_name.strip()
    user = UserService().get_public_profile(db, clean_name)
    names = ExternalIdentityService().names_for_user(db, user.id) if user else {clean_name}
    return names, {name.casefold() for name in names}


def _latest_player_elo(db: Session, username: str) -> dict:
    ratings = {}
    scope = PlayerMatchScope.resolve(db, username)
    rows = (
        db.query(MatchParticipant, Match)
        .join(Match, Match.id == MatchParticipant.match_id)
        .filter(
            scope._predicate(MatchParticipant.nickname, MatchParticipant.player_uuid),
            MatchParticipant.is_observer.is_(False),
            MatchParticipant.elo.isnot(None),
            Match.rating_patch_family.in_(("patch_202", "ennorath")),
        )
        .order_by(Match.match_date.desc(), Match.id.desc())
        .all()
    )
    for participant, match in rows:
        if is_unverified_rating(match, participant.player_uuid, participant.nickname):
            continue
        patch = match.rating_patch_family
        if patch not in ratings:
            ratings[patch] = round(float(participant.elo))
        if len(ratings) == 2:
            break
    return ratings


def _public_identity_payload(user: UserModel) -> dict:
    aliases = sorted({
        alias.nickname
        for identity in user.external_identities
        for alias in identity.aliases
        if alias.nickname
    }, key=str.casefold)
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "aliases": aliases,
        "is_admin": bool(user.role and user.role.name == "admin"),
        "titles": [
            {
                "id": assignment.title.id,
                "name": assignment.title.name,
                "description": assignment.title.description,
                "name_en": assignment.title.name_en,
                "description_en": assignment.title.description_en,
                "name_de": assignment.title.name_de,
                "description_de": assignment.title.description_de,
                "image_url": assignment.title.image_url,
            }
            for assignment in user.title_assignments
            if assignment.title and assignment.title.is_active
        ],
    }


@router.get("/identity-directory")
def get_public_identity_directory(db: Session = Depends(get_db)):
    users = (
        db.query(UserModel)
        .outerjoin(Role, Role.id == UserModel.role_id)
        .options(
            joinedload(UserModel.role),
            selectinload(UserModel.title_assignments).joinedload(UserTitle.title),
            selectinload(UserModel.external_identities).selectinload(ExternalPlayerIdentity.aliases),
        )
        .filter(
            UserModel.is_active.is_(True),
            or_(
                Role.name == "admin",
                UserModel.title_assignments.any(),
                UserModel.display_name.isnot(None),
            ),
        )
        .order_by(func.lower(UserModel.username).asc())
        .all()
    )
    return {"players": [_public_identity_payload(user) for user in users]}

@router.get("/me", response_model=User)
async def read_users_me(
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Получить информацию о текущем пользователе"""
    user_service = UserService()
    player_stats = user_service.get_user_statistics(db, current_user.username)
    
    user_data = User(
        id=current_user.id,
        username=current_user.username,
        display_name=current_user.display_name,
        email=current_user.email,
        balance=current_user.balance,
        level=current_user.level,
        experience=current_user.experience,
        avatar_url=current_user.avatar_url,
        language=current_user.language,
        allow_clan_invites=current_user.allow_clan_invites,
        telegram_url=current_user.telegram_url,
        twitch_url=current_user.twitch_url,
        youtube_url=current_user.youtube_url,
        is_active=current_user.is_active,
        is_claimed=current_user.is_claimed,
        role=current_user.role,
        created_at=current_user.created_at,
        player_statistics=player_stats,
        external_identity_status=current_user.external_identity_status,
        is_admin_impersonation=getattr(
            current_user,
            "_is_admin_impersonation",
            False,
        ),
        impersonated_by_username=getattr(
            current_user,
            "_impersonated_by_username",
            None,
        ),
    )
    return user_data


@router.post("/{user_id:int}/impersonate", response_model=SessionUserSummary)
def impersonate_user_for_testing(
    user_id: int,
    request: Request,
    response: Response,
    current_session: UserSession = Depends(get_current_session),
    current_admin: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Переключает реального администратора на серверную сессию пользователя."""
    if current_session.is_impersonation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "nested_impersonation_forbidden"},
        )
    target = db.query(UserModel).filter(UserModel.id == user_id).first()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "user_not_found"},
        )

    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    session_service = SessionService()
    try:
        issue = session_service.rotate(
            db,
            token,
            target,
            ip_address=request.client.host[:64] if request.client else None,
            user_agent=(
                request.headers["user-agent"][:500]
                if request.headers.get("user-agent")
                else None
            ),
            impersonated_by_user_id=current_admin.id,
            commit=False,
        )
        AdminAuditService().record(
            db,
            actor_user_id=current_admin.id,
            action="user_impersonation_started",
            entity_type="user",
            entity_id=target.id,
            after_data={"effective_user_id": target.id},
        )
        db.commit()
    except InvalidSession as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_session"},
        ) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "session_transition_failed"},
        ) from exc

    target._is_admin_impersonation = True
    target._impersonated_by_username = current_admin.username
    set_session_cookie(response, issue.token)
    return SessionUserSummary.model_validate(target).model_copy(
        update={
            "is_admin_impersonation": True,
            "impersonated_by_username": current_admin.username,
        }
    )


@router.post("/me/external-identity/verification-request")
def request_external_identity_verification(
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Отправить или повторно отправить внешний игровой аккаунт на проверку."""
    from app.services.external_identity_service import ExternalIdentityService

    try:
        identity = ExternalIdentityService().request_verification(db, current_user)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {
        "status": identity.verification_status,
        "nickname": identity.current_nickname,
    }


@router.get("/external-identities/pending")
def get_pending_external_identity_verifications(
    current_admin: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Очередь ручной проверки игровых аккаунтов."""
    from app.models.external_identity import ExternalPlayerIdentity

    rows = (
        db.query(ExternalPlayerIdentity, UserModel)
        .join(UserModel, UserModel.id == ExternalPlayerIdentity.user_id)
        .filter(ExternalPlayerIdentity.verification_status == "pending")
        .order_by(
            ExternalPlayerIdentity.claimed_at.asc(),
            ExternalPlayerIdentity.id.asc(),
        )
        .all()
    )
    return [
        {
            "identity_id": identity.id,
            "user_id": user.id,
            "username": user.username,
            "nickname": identity.current_nickname,
            "external_uuid": identity.external_uuid,
            "claimed_at": identity.claimed_at,
        }
        for identity, user in rows
    ]


@router.put("/{user_id:int}/external-identity/verification")
def review_external_identity_verification(
    user_id: int,
    review: IdentityVerificationReview,
    current_admin: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Подтвердить или отклонить заявку владельца игрового аккаунта."""
    from app.services.external_identity_service import ExternalIdentityService

    target_user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if target_user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    try:
        identity = ExternalIdentityService().review_verification(
            db,
            target_user=target_user,
            reviewer=current_admin,
            decision=review.decision,
            reason=review.reason,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {
        "status": identity.verification_status,
        "nickname": identity.current_nickname,
        "reviewed_user_id": target_user.id,
    }

@router.get("/", response_model=List[PublicUser])
def read_users(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db)
):
    """Получить список пользователей"""
    try:
        user_service = UserService()
        users = user_service.get_users(db, skip=skip, limit=limit)
        
        # Конвертируем SQLAlchemy модели в Pydantic схемы
        user_list = []
        for user in users:
            user_data = PublicUser(
                id=user.id,
                username=user.username,
                level=user.level,
                experience=user.experience,
                avatar_url=user.avatar_url,
                allow_clan_invites=user.allow_clan_invites,
                telegram_url=user.telegram_url,
                twitch_url=user.twitch_url,
                youtube_url=user.youtube_url,
                is_active=user.is_active,
                is_claimed=user.is_claimed,
                external_identity_status=user.external_identity_status,
                created_at=user.created_at
            )
            user_list.append(user_data)
        
        return user_list
    except Exception as e:
        print(f"Ошибка в API users: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

@router.get("/{user_id:int}", response_model=PublicUser)
def read_user(user_id: int, db: Session = Depends(get_db)):
    """Получить пользователя по ID"""
    user_service = UserService()
    user = user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Конвертируем SQLAlchemy модель в Pydantic схему
    user_data = User(
        id=user.id,
        username=user.username,
        email=user.email,
        balance=user.balance,
        level=user.level,
        experience=user.experience,
        avatar_url=user.avatar_url,
        language=user.language,
        allow_clan_invites=user.allow_clan_invites,
        telegram_url=user.telegram_url,
        twitch_url=user.twitch_url,
        youtube_url=user.youtube_url,
        is_active=user.is_active,
        is_claimed=user.is_claimed,
        external_identity_status=user.external_identity_status,
        created_at=user.created_at
    )
    return user_data

@router.get("/by-username/{username}", response_model=PublicUser)
def get_user_by_username(
    username: str,
    db: Session = Depends(get_db)
):
    """Получить пользователя по username"""
    user_service = UserService()
    user = user_service.get_or_create_public_profile(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Конвертируем SQLAlchemy модель в Pydantic схему
    user_data = User(
        id=user.id,
        username=user.username,
        email=user.email,
        balance=user.balance,
        level=user.level,
        experience=user.experience,
        avatar_url=user.avatar_url,
        language=user.language,
        allow_clan_invites=user.allow_clan_invites,
        telegram_url=user.telegram_url,
        twitch_url=user.twitch_url,
        youtube_url=user.youtube_url,
        is_active=user.is_active,
        is_claimed=user.is_claimed,
        external_identity_status=user.external_identity_status,
        role=user.role,
        created_at=user.created_at
    )
    return user_data

@router.get("/profile/{username}", response_model=PublicUser)
def get_user_profile_by_username(
    username: str,
    db: Session = Depends(get_db)
):
    """Получить профиль пользователя по username"""
    user_service = UserService()
    user = user_service.get_or_create_public_profile(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Конвертируем SQLAlchemy модель в Pydantic схему
    user_data = User(
        id=user.id,
        username=user.username,
        email=user.email,
        balance=user.balance,
        level=user.level,
        experience=user.experience,
        avatar_url=user.avatar_url,
        language=user.language,
        allow_clan_invites=user.allow_clan_invites,
        telegram_url=user.telegram_url,
        twitch_url=user.twitch_url,
        youtube_url=user.youtube_url,
        is_active=user.is_active,
        is_claimed=user.is_claimed,
        external_identity_status=user.external_identity_status,
        created_at=user.created_at
    )
    return user_data

@router.get("/profile/{username}/overview")
async def get_public_profile_overview(
    username: str,
    db: Session = Depends(get_db)
):
    """Публичный профиль: базовые данные, статистика и достижения без приватных полей."""
    user_service = UserService()
    user = user_service.get_or_create_public_profile(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    statistics = user_service.get_user_statistics(db, user.username) or {}
    try:
        statistics = await get_player_statistics(user.username, db)
    except HTTPException as error:
        if error.status_code != 404:
            raise
    achievements = UserAchievementService().get_user_achievements(db, user.id)
    public_user = {
        "id": user.id,
        "username": user.username,
        "is_claimed": user.is_claimed,
        "external_identity_status": user.external_identity_status,
        "level": user.level,
        "experience": user.experience,
        "avatar_url": user.avatar_url,
        "language": user.language,
        "created_at": user.created_at,
        "player_statistics": statistics,
        **_public_identity_payload(user),
    }
    public_achievements = []
    for item in achievements:
        achievement = item.achievement
        if not achievement or not achievement.is_available:
            continue
        public_achievements.append({
            "id": item.id,
            "user_id": item.user_id,
            "achievement_id": item.achievement_id,
            "progress": item.progress,
            "is_completed": item.is_completed,
            "completed_at": item.completed_at,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "achievement": {
                "id": achievement.id,
                "name": achievement.name,
                "description": achievement.description,
                "icon": achievement.icon,
                "category": achievement.category,
                "rarity": achievement.rarity,
                "points": achievement.points,
                "requirement_type": achievement.requirement_type,
                "requirement_value": achievement.requirement_value,
                "target_value": achievement.target_value,
                "reward_amount": achievement.reward_amount,
                "achievement_type": achievement.achievement_type,
                "is_available": achievement.is_available,
                "created_at": achievement.created_at,
            },
        })

    return {
        "user": public_user,
        "statistics": statistics,
        "achievements": public_achievements,
    }

@router.get("/{user_id:int}/clan")
def get_user_clan(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Получить клан пользователя по ID"""
    from app.services.clan_service import ClanService
    
    clan_service = ClanService()
    clan_member = clan_service.get_user_clan(db, user_id)
    
    if clan_member is None:
        return {"message": "Пользователь не состоит в клане"}
    
    # Получаем информацию о клане
    clan = clan_service.get_clan(db, clan_member.clan_id)
    
    if clan is None:
        return {"message": "Клан не найден"}
    
    return {
        "id": clan.id,
        "name": clan.name,
        "description": clan.description,
        "created_at": clan.created_at,
        "leader_id": clan.leader_id,
        "member_rank": clan_member.rank,
        "joined_at": clan_member.joined_at,
        "is_trader": bool(clan_member.is_trader),
        "is_warlord": bool(clan_member.is_warlord),
    }

@router.get("/search/{username}", response_model=List[PublicUser])
def search_users_by_username(
    username: str,
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Поиск пользователей по имени"""
    user_service = UserService()
    users = user_service.search_users_by_username(db, username, skip=skip, limit=limit)
    
    # Конвертируем SQLAlchemy модели в Pydantic схемы
    user_list = []
    for user in users:
        user_data = User(
            id=user.id,
            username=user.username,
            email=user.email,
            balance=user.balance,
            level=user.level,
            experience=user.experience,
            avatar_url=user.avatar_url,
            language=user.language,
            telegram_url=user.telegram_url,
            twitch_url=user.twitch_url,
            youtube_url=user.youtube_url,
            is_active=user.is_active,
            is_claimed=user.is_claimed,
            created_at=user.created_at
        )
        user_list.append(user_data)
    
    return user_list

@router.get("/search/clanless/{username}", response_model=List[PublicUser])
def search_users_without_clan(
    username: str,
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Поиск пользователей без клана по имени"""
    try:
        from app.services.clan_service import ClanService
        
        # Получаем пользователей по имени
        user_service = UserService()
        users = user_service.search_users_by_username(db, username, skip=skip, limit=limit)
        
        # Фильтруем пользователей без клана
        clan_service = ClanService()
        users_without_clan = []
        
        for user in users:
            # Проверяем, есть ли у пользователя клан
            clan_member = clan_service.get_user_clan(db, user.id)
            if clan_member is None:
                user_data = User(
                    id=user.id,
                    username=user.username,
                    email=user.email,
                    balance=user.balance,
                    level=user.level,
                    experience=user.experience,
                    avatar_url=user.avatar_url,
                    language=user.language,
                    allow_clan_invites=user.allow_clan_invites,
                    telegram_url=user.telegram_url,
                    twitch_url=user.twitch_url,
                    youtube_url=user.youtube_url,
                    is_active=user.is_active,
                    is_claimed=user.is_claimed,
                    created_at=user.created_at
                )
                users_without_clan.append(user_data)
        
        return users_without_clan
        
    except Exception as e:
        print(f"Error searching users without clan: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/{user_id:int}/balance")
def update_user_balance(
    user_id: int,
    balance_update: BalanceUpdate,
    current_user: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Изменить баланс пользователя от имени администратора."""
    if balance_update.amount == 0 or abs(balance_update.amount) > 1_000_000:
        raise HTTPException(status_code=400, detail="Сумма должна быть от -1000000 до 1000000 и не равна нулю")

    target_user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if target_user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    old_balance = target_user.balance or 0
    if old_balance + balance_update.amount < 0:
        raise HTTPException(status_code=400, detail="Баланс пользователя не может стать отрицательным")

    user_service = UserService()
    user = user_service.update_balance(db, user_id, balance_update.amount)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    AdminAuditService().record(
        db,
        actor_user_id=current_user.id,
        action="user_balance_adjusted",
        entity_type="user",
        entity_id=user.id,
        before_data={"balance": old_balance},
        after_data={"balance": user.balance, "delta": balance_update.amount},
        reason=balance_update.reason,
    )
    db.commit()
    return {"message": "Баланс успешно обновлен", "new_balance": user.balance}

@router.post("/avatar")
async def upload_current_user_avatar(
    avatar: UploadFile = File(...),
    crop_x: float = Form(None),
    crop_y: float = Form(None),
    crop_width: float = Form(None),
    crop_height: float = Form(None),
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Загрузить аватар текущего пользователя"""
    try:
        print(f"Starting avatar upload for user {current_user.id}")
        print(f"File info: {avatar.filename}, {avatar.content_type}, {avatar.size}")
        
        # Проверяем тип файла (разрешаем все типы изображений включая GIF)
        if not avatar.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Файл должен быть изображением (JPG, PNG, GIF и т.д.)")
        
        # Создаем директорию для загрузки в public папке React приложения
        upload_dir = os.path.join(settings.UPLOAD_DIR, "users")
        print(f"Creating directory: {upload_dir}")
        os.makedirs(upload_dir, exist_ok=True)
        print(f"Directory created/verified: {upload_dir}")
    
        # Генерируем имя файла
        file_extension = avatar.filename.split('.')[-1]
        filename = f"user_{current_user.id}_{uuid.uuid4().hex}.{file_extension}"
        file_path = os.path.join(upload_dir, filename)
        print(f"Generated filename: {filename}")
        print(f"Full file path: {file_path}")
        
        # Читаем файл
        print("Reading file content...")
        content = await avatar.read()
        print(f"File content size: {len(content)} bytes")
        
        # Обрабатываем изображение
        print("Processing image...")
        process_avatar_image(content, file_path, crop_x, crop_y, crop_width, crop_height)
        print("Image processing completed")
        
        # Проверяем, что файл действительно создан
        print("Checking if file exists...")
        if not os.path.exists(file_path):
            print(f"ERROR: File does not exist at {file_path}")
            raise HTTPException(status_code=500, detail="Ошибка при сохранении файла")
        print(f"File exists: {file_path}")
        
        avatar_url = f"/images/users/{filename}"
        print(f"Avatar URL: {avatar_url}")
        
        print("Updating user in database...")
        user_service = UserService()
        user = user_service.update_avatar(db, current_user.id, avatar_url)
        if user is None:
            print("ERROR: User not found in database")
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        print("User updated successfully")
        
        print(f"Avatar upload completed successfully: {file_path}")
        return {"message": "Аватар успешно загружен", "avatar_url": avatar_url}
        
    except Exception as e:
        print(f"ERROR in avatar upload: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке аватарки: {str(e)}")

@router.post("/{user_id:int}/avatar")
async def upload_user_avatar(
    user_id: int,
    avatar: UploadFile = File(...),
    crop_x: float = Form(None),
    crop_y: float = Form(None),
    crop_width: float = Form(None),
    crop_height: float = Form(None),
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Загрузить аватар пользователя"""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Можно загружать аватар только для себя")
    
    # Проверяем тип файла (разрешаем все типы изображений включая GIF)
    if not avatar.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Файл должен быть изображением (JPG, PNG, GIF и т.д.)")
    
    # Создаем директорию для загрузки в public папке React приложения
    upload_dir = os.path.join(settings.UPLOAD_DIR, "users")
    os.makedirs(upload_dir, exist_ok=True)
    
    # Генерируем имя файла
    file_extension = avatar.filename.split('.')[-1]
    filename = f"user_{user_id}_{uuid.uuid4().hex}.{file_extension}"
    file_path = os.path.join(upload_dir, filename)
    
    # Читаем файл
    content = await avatar.read()
    
    # Обрабатываем изображение
    process_avatar_image(content, file_path, crop_x, crop_y, crop_width, crop_height)
    
    avatar_url = f"/images/users/{filename}"
    
    user_service = UserService()
    user = user_service.update_avatar(db, user_id, avatar_url)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    return {"message": "Аватар успешно загружен", "avatar_url": avatar_url}

@router.put("/{user_id:int}", response_model=User)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Обновить данные пользователя"""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Можно обновлять только свой профиль")
    
    user_service = UserService()
    user = user_service.update_user(db, user_id, user_update)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user 

@router.get("/player-statistics/{username}")
async def get_player_statistics(username: str, db: Session = Depends(get_db)):
    """Получить статистику игрока из базы данных матчей"""
    try:
        scope = PlayerMatchScope.resolve(db, username)
        matches = scope.query(db).all()
        live_ratings = await arena_current_ratings.for_user(scope.user)
        
        if not matches:
            return {
                "total_matches": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "factions_used": {},
                "maps_played": {},
                "recent_matches": [],
                "current_elo": live_ratings,
                "elo_history": {"patch_202": [], "ennorath": []},
            }
        
        # Подсчитываем статистику используя SQLAlchemy ORM
        def player_entry(match):
            return scope.participant(match)

        total_matches = len(matches)
        wins = sum(
            1
            for match in matches
            if (
                player_entry(match).is_winner
                if player_entry(match) is not None
                else scope.is_winner(match)
            )
        )
        losses = total_matches - wins
        win_rate = (wins / total_matches * 100) if total_matches > 0 else 0
        
        # Подсчитываем фракции
        factions_used = {}
        maps_played = {}
        for match in matches:
            entry = player_entry(match)
            if entry is not None:
                faction = entry.faction
                is_win = entry.is_winner
            elif scope.is_winner(match):
                faction, is_win = match.winner_faction, True
            else:
                faction, is_win = match.loser_faction, False
            
            map_name = match.map_name or "Unknown map"
            if map_name not in maps_played:
                maps_played[map_name] = {
                    "total": 0,
                    "wins": 0,
                    "losses": 0,
                    "map_preview_url": map_preview_storage.public_url(match.map_name),
                }
            maps_played[map_name]["total"] += 1

            if faction not in factions_used:
                factions_used[faction] = {"total": 0, "wins": 0, "losses": 0}
            
            factions_used[faction]["total"] += 1
            if is_win:
                factions_used[faction]["wins"] += 1
                maps_played[map_name]["wins"] += 1
            else:
                factions_used[faction]["losses"] += 1
                maps_played[map_name]["losses"] += 1
        
        # Вычисляем процент побед для каждой фракции
        for faction in factions_used:
            total = factions_used[faction]["total"]
            faction_wins = factions_used[faction]["wins"]
            factions_used[faction]["win_rate"] = round((faction_wins / total * 100), 2) if total > 0 else 0

        for map_stats in maps_played.values():
            map_stats["win_rate"] = round((map_stats["wins"] / map_stats["total"] * 100), 2) if map_stats["total"] > 0 else 0

        elo_history = {"patch_202": [], "ennorath": []}
        rating_matches = sorted(
            matches,
            key=lambda item: as_utc(
                item.ratings_captured_at or item.match_date or item.created_at,
            ),
        )
        for match in rating_matches:
            patch_family = match.rating_patch_family
            if patch_family not in elo_history:
                continue

            entry = player_entry(match)
            if is_unverified_rating(match, entry.player_uuid if entry else None,
                                    entry.nickname if entry else username):
                continue
            elo = entry.elo if entry is not None else (
                match.winner_elo if scope.is_winner(match) else match.loser_elo
            )
            if elo is None:
                continue

            captured_at = (
                match.ratings_captured_at
                or match.created_at
                or match.match_date
            )
            elo_history[patch_family].append({
                "match_id": match.match_id,
                "elo": round(float(elo), 2),
                "captured_at": captured_at.isoformat() if captured_at else None,
                "played_at": match.match_date.isoformat() if match.match_date else None,
            })

        for patch_family in elo_history:
            elo_history[patch_family] = elo_history[patch_family][-100:]

        current_elo = {
            patch_family: history[-1]["elo"]
            for patch_family, history in elo_history.items()
            if history
        }
        current_elo.update(live_ratings)
        
        # Получаем последние 5 матчей
        recent_matches = scope.query(db).order_by(Match.match_date.desc()).limit(5).all()
        
        recent_matches_data = []
        for match in recent_matches:
            entry = player_entry(match)
            if entry is not None:
                result = "win" if entry.is_winner else "loss"
                player_faction = entry.faction
                player_elo = entry.elo
                opponents = [
                    participant
                    for participant in (match.participants or [])
                    if participant.is_winner != entry.is_winner and not participant.is_observer
                ]
                opponent = ", ".join(item.nickname for item in opponents)
                opponent_faction = opponents[0].faction if opponents else None
            elif scope.is_winner(match):
                result, player_faction = "win", match.winner_faction
                player_elo = match.winner_elo
                opponent_faction, opponent = match.loser_faction, match.loser_player
            else:
                result, player_faction = "loss", match.loser_faction
                player_elo = match.loser_elo
                opponent_faction, opponent = match.winner_faction, match.winner_player
            
            recent_matches_data.append({
                "match_id": match.match_id,
                "result": result,
                "player_faction": player_faction,
                "opponent_faction": opponent_faction,
                "opponent": opponent,
                "opponents": [item.nickname for item in opponents] if entry is not None else [opponent],
                "date": match.match_date.strftime("%d.%m.%Y"),
                "map": match.map_name or "Неизвестная карта",
                "game_mode": match.gamemode_name or match.game_mode,
                "elo": round(float(player_elo), 2) if player_elo is not None else None,
                "rating_patch_family": match.rating_patch_family,
            })
        
        return {
            "total_matches": total_matches,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 2),
            "factions_used": factions_used,
            "maps_played": maps_played,
            "recent_matches": recent_matches_data,
            "current_elo": current_elo,
            "elo_history": elo_history,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting player statistics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") 

@router.get("/{username}/matches/all")
async def get_all_user_matches(
    username: str, 
    db: Session = Depends(get_db)
):
    """Получить все матчи пользователя"""
    try:
        scope = PlayerMatchScope.resolve(db, username)
        matches = scope.query(db).order_by(Match.match_date.desc()).all()
        
        matches_data = []
        for match in matches:
            # Определяем результат для текущего игрока
            entry = scope.participant(match)
            if entry is not None:
                result = "win" if entry.is_winner else "loss"
                player_faction = entry.faction
                opponents = [
                    participant
                    for participant in (match.participants or [])
                    if participant.is_winner != entry.is_winner and not participant.is_observer
                ]
                opponent_faction = opponents[0].faction if opponents else None
                opponent = ", ".join(item.nickname for item in opponents)
            elif scope.is_winner(match):
                result = "win"
                player_faction = match.winner_faction
                opponent_faction = match.loser_faction
                opponent = match.loser_player
            else:
                result = "loss"
                player_faction = match.loser_faction
                opponent_faction = match.winner_faction
                opponent = match.winner_player
            
            matches_data.append({
                "id": match.match_id,
                "match_date": match.match_date.isoformat(),
                "map_name": match.map_name or "Неизвестная карта",
                "map_preview_url": map_preview_storage.public_url(match.map_name),
                "winner_player": match.winner_player,
                "loser_player": match.loser_player,
                "winner_faction": match.winner_faction,
                "loser_faction": match.loser_faction,
                "player_faction": player_faction,
                "opponent_faction": opponent_faction,
                "opponent_player": opponent,
                "opponents": [item.nickname for item in opponents] if entry is not None else [opponent],
                "participants": [
                    {
                        "nickname": item.nickname,
                        "faction": item.faction,
                        "team": item.team,
                        "is_winner": item.is_winner,
                        "elo": item.elo,
                    }
                    for item in (match.participants or [])
                    if not item.is_observer
                ],
                "duration": match.duration,
                "game_mode": match.gamemode_name or match.game_mode,
                "patch_version": match.patch_version,
            })
        
        return matches_data
        
    except Exception as e:
        print(f"Error getting all user matches: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get(
    "/{username}/territory-contributions",
    response_model=TerritoryContributionResponse,
)
def get_territory_contributions(
    username: str,
    season_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
):
    """Публичный вклад игрока в войны за территории по сохранённым снимкам."""
    user = UserService().get_public_profile(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return TerritoryContributionService().calculate(
        db,
        user=user,
        season_id=season_id,
    )


@router.get("/{user_id:int}/stats")
async def get_user_stats(
    user_id: int,
    clan_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """Получить статистику пользователя по ID"""
    try:
        # Получаем пользователя по ID
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        
        # Получаем статистику пользователя
        user_service = UserService()
        player_stats = user_service.get_user_statistics(db, user.username)
        
        # Добавляем уровень и опыт из модели пользователя
        stats = {
            "total_matches": player_stats.get("total_matches", 0),
            "wins": player_stats.get("wins", 0),
            "losses": player_stats.get("losses", 0),
            "win_rate": player_stats.get("win_rate", 0),
            "level": user.level,
            "experience": user.experience
        }
        if clan_id is not None:
            clan = db.query(Clan).filter(Clan.id == clan_id).first()
            if not clan:
                raise HTTPException(status_code=404, detail="Клан не найден")
            clan_experience = ClanExperienceService().calculate(
                db,
                user,
                clan_id,
            )
            stats.update(clan_experience)
            stats["experience"] = clan_experience["clan_experience"]
            stats["total_matches"] = clan_experience["clan_matches"]
            stats["wins"] = clan_experience["clan_wins"]
            stats["losses"] = clan_experience["clan_losses"]
            stats["win_rate"] = round(
                clan_experience["clan_wins"]
                / clan_experience["clan_matches"]
                * 100,
                2,
            ) if clan_experience["clan_matches"] else 0
            stats["elo_ratings"] = _latest_player_elo(db, user.username)
            stats['elo_ratings'].update(await arena_current_ratings.for_user(user))
            stats["elo_patch"] = clan.preferred_patch or "all"
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting user stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
