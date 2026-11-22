from typing import List
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Body
from fastapi.responses import FileResponse
from pydantic import ValidationError
from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.auth import (
    get_current_active_user,
    get_current_admin_user,
    get_onboarded_active_user,
)
from app.core.permissions import ClanPermission, is_admin, require_clan_permission
from app.models.user import User as UserModel
from app.schemas.clan import (
    Clan, ClanCreate, ClanUpdate, ClanWithMemberCount,
    ClanInvite, ClanInviteCreate, ClanInviteWithDetails,
    ClanMemberCreate, ClanMemberWithUser, ClanApplication, ClanApplicationCreate,
    ClanApplicationUpdate, ClanApplicationWithDetails, ClanMemberRoleUpdate,
    ClanMemberWarlordUpdate,
    KickMemberRequest, TransferLeadershipRequest, ClanMapColorState
    ,MarketOfferCreate, MarketOfferAccept, ClanWarReadiness
)
from app.schemas.clan_asset import (
    ClanAssetAdminPayload,
    ClanAssetPurchase,
    ClanRelicLoadoutUpdate,
)
from app.models.clan_asset import ClanAsset
from app.services.clan_economy_service import ClanEconomyService
from app.services.clan_service import ClanService
from app.services.market_service import ClanMarketService
from app.api.v1.campaign_guard import require_campaign_running
from app.services.war_service import ClanWarService
from app.utils.image_processor import process_avatar_image
from app.config import settings
import os
import uuid
from pathlib import Path
from threading import Lock

router = APIRouter(prefix="/clans", tags=["clans"])

economy_service = ClanEconomyService()
market_service = ClanMarketService()
map_emblem_cache_lock = Lock()
MAX_CLAN_IMAGE_BYTES = 5 * 1024 * 1024
SUPPORTED_CLAN_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}


def read_validated_clan_image(upload: UploadFile | None, field_name: str) -> bytes | None:
    """Читает и проверяет изображение до любых изменений в базе данных."""
    if upload is None:
        return None
    content_type = (upload.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"{field_name}: выберите изображение")
    content = upload.file.read(MAX_CLAN_IMAGE_BYTES + 1)
    if len(content) > MAX_CLAN_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail=f"{field_name}: файл больше 5 МБ")
    if not content:
        raise HTTPException(status_code=400, detail=f"{field_name}: файл пуст")
    try:
        with Image.open(BytesIO(content)) as image:
            detected_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name}: файл повреждён или имеет неподдерживаемый формат",
        ) from error
    if detected_format not in SUPPORTED_CLAN_IMAGE_FORMATS:
        raise HTTPException(status_code=400, detail=f"{field_name}: формат не поддерживается")
    return content


def normalized_avatar_extension(upload: UploadFile) -> str:
    extension = Path(upload.filename or "").suffix.lower()
    return extension if extension in {".png", ".jpg", ".jpeg", ".webp", ".gif"} else ".webp"


def remove_map_emblem_preview(avatar_url: str | None) -> None:
    """Удаляет устаревшее превью, не затрагивая исходную эмблему."""
    if not avatar_url:
        return
    normalized_url = avatar_url.split("?", 1)[0]
    prefix = "/images/clans/"
    if not normalized_url.startswith(prefix):
        return
    filename = normalized_url.removeprefix(prefix)
    if not filename or Path(filename).name != filename:
        return
    preview_path = (
        Path(settings.UPLOAD_DIR)
        / "clans"
        / "map-emblems"
        / f"{filename}.webp"
    )
    preview_path.unlink(missing_ok=True)


@router.get("/map-emblem/{filename}", include_in_schema=False)
def get_static_map_emblem(filename: str):
    """Возвращает статичный первый кадр эмблемы для стратегической карты."""
    safe_filename = Path(filename).name
    if safe_filename != filename:
        raise HTTPException(status_code=400, detail="Недопустимое имя файла")

    source_path = Path(settings.UPLOAD_DIR) / "clans" / safe_filename
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail="Эмблема клана не найдена")

    preview_dir = Path(settings.UPLOAD_DIR) / "clans" / "map-emblems"
    preview_path = preview_dir / f"{source_path.name}.webp"
    with map_emblem_cache_lock:
        preview_dir.mkdir(parents=True, exist_ok=True)
        source_changed = (
            not preview_path.exists()
            or preview_path.stat().st_mtime < source_path.stat().st_mtime
        )
        if source_changed:
            temporary_path = preview_dir / f".{source_path.name}.{uuid.uuid4().hex}.tmp"
            try:
                if not process_avatar_image(
                    source_path.read_bytes(),
                    str(temporary_path),
                    preserve_animation=False,
                ):
                    raise HTTPException(
                        status_code=422,
                        detail="Не удалось обработать эмблему клана",
                    )
                temporary_path.replace(preview_path)
            finally:
                temporary_path.unlink(missing_ok=True)

    return FileResponse(preview_path, media_type="image/webp")


@router.get("/map-colors", response_model=ClanMapColorState)
def read_clan_map_colors(
    clan_id: int | None = None,
    db: Session = Depends(get_db),
):
    return ClanService().get_map_color_state(db, clan_id=clan_id)


@router.get("/assets/admin")
def get_all_clan_assets_for_admin(
    db: Session = Depends(get_db),
    _: UserModel = Depends(get_current_admin_user),
):
    return db.query(ClanAsset).order_by(ClanAsset.id).all()


@router.post("/assets/admin")
def create_clan_asset(
    payload: ClanAssetAdminPayload,
    db: Session = Depends(get_db),
    _: UserModel = Depends(get_current_admin_user),
):
    if db.query(ClanAsset).filter(ClanAsset.key == payload.key).first():
        raise HTTPException(
            status_code=409,
            detail="Реликвия с таким техническим ключом уже существует",
        )
    asset = ClanAsset(**payload.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.put("/assets/admin/{asset_id:int}")
def update_clan_asset(
    asset_id: int,
    payload: ClanAssetAdminPayload,
    db: Session = Depends(get_db),
    _: UserModel = Depends(get_current_admin_user),
):
    asset = db.query(ClanAsset).filter(ClanAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Реликвия не найдена")
    duplicate = (
        db.query(ClanAsset)
        .filter(ClanAsset.key == payload.key, ClanAsset.id != asset_id)
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="Реликвия с таким техническим ключом уже существует",
        )
    for field, value in payload.model_dump().items():
        setattr(asset, field, value)
    db.commit()
    db.refresh(asset)
    return asset


@router.delete("/assets/admin/{asset_id:int}")
def disable_clan_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    _: UserModel = Depends(get_current_admin_user),
):
    asset = db.query(ClanAsset).filter(ClanAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Реликвия не найдена")
    asset.is_available = False
    db.commit()
    return {"message": "Реликвия отключена и сохранена в истории"}

@router.get("/", response_model=List[ClanWithMemberCount])
def read_clans(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db)
):
    """Получить список кланов"""
    clan_service = ClanService()
    clans = clan_service.get_clans(db, skip=skip, limit=limit)
    
    # Конвертируем SQLAlchemy модели в Pydantic схемы
    clan_list = []
    for clan in clans:
        # Получаем количество участников
        member_count = len(clan_service.get_clan_members(db, clan.id))
        territory_count = len(clan.owned_territories)
        
        clan_data = ClanWithMemberCount(
            id=clan.id,
            name=clan.name,
            motto=clan.motto,
            description=clan.description,
            leader_id=clan.leader_id,
            avatar_url=clan.avatar_url,
            map_emblem_url=clan.map_emblem_url,
            map_color=clan.map_color,
            map_color_change_used=clan.map_color_change_used,
            level=clan_service.get_public_level(db, clan),
            experience=clan.experience,
            max_members=clan.max_members,
            resources=clan.resources or 0,
            base_influence=clan.base_influence or 0,
            territory_points=clan.territory_points or 0,
            gold=clan.gold or 0,
            iron=clan.iron or 0,
            wood=clan.wood or 0,
            food=clan.food or 0,
            mithril=clan.mithril or 0,
            is_admin_clan=clan.is_admin_clan,
            is_recruiting=clan.is_recruiting,
            is_deleted=clan.is_deleted,
            deleted_at=clan.deleted_at,
            preferred_patch=clan.preferred_patch or "all",
            next_attack_at=clan.next_attack_at,
            created_at=clan.created_at,
            member_count=member_count,
            territory_count=territory_count,
        )
        clan_list.append(clan_data)
    
    return clan_list


@router.get("/{clan_id:int}/economy")
def get_clan_economy(clan_id: int, db: Session = Depends(get_db)):
    return economy_service.get_clan_economy(db, clan_id)


@router.get("/{clan_id:int}/war-readiness", response_model=ClanWarReadiness)
def get_clan_war_readiness(
    clan_id: int,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return ClanWarService().get_war_readiness(db, clan_id, current_user)


@router.get("/{clan_id:int}/assets")
def get_clan_assets(clan_id: int, db: Session = Depends(get_db)):
    return economy_service.list_assets(db, clan_id)


@router.post("/{clan_id:int}/assets/purchase")
def purchase_clan_asset(
    clan_id: int,
    purchase: ClanAssetPurchase,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    require_campaign_running(db)
    return economy_service.purchase_asset(db, clan_id, purchase.asset_id, current_user)


@router.put("/{clan_id:int}/assets/loadout")
def update_clan_relic_loadout(
    clan_id: int,
    payload: ClanRelicLoadoutUpdate,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    require_campaign_running(db)
    return economy_service.update_relic_loadout(
        db,
        clan_id,
        payload.asset_ids,
        current_user,
    )


@router.put("/{clan_id:int}/members/{user_id:int}/trader")
def set_clan_trader(
    clan_id: int,
    user_id: int,
    is_trader: bool = Body(..., embed=True),
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    return economy_service.set_trader(db, clan_id, user_id, is_trader, current_user)


@router.put(
    "/{clan_id:int}/members/{user_id:int}/role",
    response_model=ClanMemberWithUser,
)
def set_clan_member_role(
    clan_id: int,
    user_id: int,
    payload: ClanMemberRoleUpdate,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    ClanService().set_member_role(
        db,
        clan_id,
        user_id,
        payload.role,
        current_user,
    )
    member = next(
        (
            item
            for item in ClanService().get_clan_members(db, clan_id)
            if item["user_id"] == user_id
        ),
        None,
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Участник клана не найден")
    return ClanMemberWithUser(**member)


@router.put(
    "/{clan_id:int}/members/{user_id:int}/warlord",
    response_model=ClanMemberWithUser,
)
def set_clan_member_warlord(
    clan_id: int,
    user_id: int,
    payload: ClanMemberWarlordUpdate,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    ClanService().set_member_warlord(
        db,
        clan_id,
        user_id,
        payload.is_warlord,
        current_user,
    )
    member = next(
        (
            item
            for item in ClanService().get_clan_members(db, clan_id)
            if item["user_id"] == user_id
        ),
        None,
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Участник клана не найден")
    return ClanMemberWithUser(**member)


@router.get("/market/offers")
def read_market_offers(
    clan_id: int | None = None,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return market_service.list_market(db, clan_id)


@router.post("/market/offers")
def create_market_offer(
    payload: MarketOfferCreate,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    require_campaign_running(db)
    return market_service.create_offer(
        db,
        creator_clan_id=payload.creator_clan_id,
        give_resource=payload.give_resource,
        give_amount=payload.give_amount,
        receive_resource=payload.receive_resource,
        receive_amount=payload.receive_amount,
        expires_in_days=payload.expires_in_days,
        current_user=current_user,
    )


@router.post("/market/offers/{offer_id:int}/accept")
def accept_market_offer(
    offer_id: int,
    payload: MarketOfferAccept,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    require_campaign_running(db)
    return market_service.accept_offer(
        db,
        offer_id=offer_id,
        accepter_clan_id=payload.accepter_clan_id,
        current_user=current_user,
    )


@router.post("/market/offers/{offer_id:int}/cancel")
def cancel_market_offer(
    offer_id: int,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    require_campaign_running(db)
    return market_service.cancel_offer(
        db,
        offer_id=offer_id,
        current_user=current_user,
    )

@router.post("/", response_model=Clan)
def create_clan(
    clan: ClanCreate,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Создать новый клан"""
    clan_service = ClanService()
    
    # Проверяем, что пользователь не состоит уже в клане
    existing_clan = clan_service.get_user_clan(db, current_user.id)
    if existing_clan:
        raise HTTPException(status_code=400, detail="Пользователь уже состоит в клане")
    
    return clan_service.create_clan(db, clan, current_user.id)


@router.post("/with-assets", response_model=Clan)
def create_clan_with_assets(
    name: str = Form(...),
    motto: str = Form(""),
    description: str = Form(""),
    preferred_patch: str = Form("all"),
    map_color: str = Form(...),
    avatar: UploadFile | None = File(None),
    map_emblem: UploadFile | None = File(None),
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    """Создаёт полностью оформленный клан одной серверной операцией."""
    if not map_color.strip():
        raise HTTPException(status_code=422, detail="Выберите цвет владений")
    try:
        clan_payload = ClanCreate(
            name=name.strip(),
            motto=motto.strip() or None,
            description=description.strip() or None,
            preferred_patch=preferred_patch,
            map_color=map_color,
        )
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error

    temporary_paths: list[Path] = []
    final_paths: list[Path] = []
    upload_root = Path(settings.UPLOAD_DIR) / "clans"
    pending_dir = upload_root / ".pending"
    avatar_content = None
    emblem_content = None

    try:
        avatar_content = read_validated_clan_image(avatar, "Аватарка клана")
        emblem_content = read_validated_clan_image(map_emblem, "Эмблема на карте")
        pending_dir.mkdir(parents=True, exist_ok=True)

        pending_avatar = None
        if avatar_content is not None and avatar is not None:
            avatar_extension = normalized_avatar_extension(avatar)
            pending_avatar = pending_dir / f"avatar-{uuid.uuid4().hex}{avatar_extension}"
            temporary_paths.append(pending_avatar)
            if not process_avatar_image(avatar_content, str(pending_avatar)):
                raise HTTPException(status_code=400, detail="Не удалось обработать аватарку клана")

        pending_emblem = None
        if emblem_content is not None:
            pending_emblem = pending_dir / f"emblem-{uuid.uuid4().hex}.webp"
            temporary_paths.append(pending_emblem)
            if not process_avatar_image(
                emblem_content,
                str(pending_emblem),
                preserve_animation=False,
            ):
                raise HTTPException(status_code=400, detail="Не удалось обработать эмблему на карте")

        clan_service = ClanService()
        db_clan = clan_service.create_clan_pending(db, clan_payload, current_user.id)

        if pending_avatar is not None and avatar is not None:
            avatar_filename = (
                f"clan_{db_clan.id}_{uuid.uuid4().hex}{normalized_avatar_extension(avatar)}"
            )
            avatar_path = upload_root / avatar_filename
            avatar_path.parent.mkdir(parents=True, exist_ok=True)
            pending_avatar.replace(avatar_path)
            final_paths.append(avatar_path)
            db_clan.avatar_url = f"/images/clans/{avatar_filename}"

        if pending_emblem is not None:
            emblem_filename = f"clan_{db_clan.id}_{uuid.uuid4().hex}.webp"
            emblem_path = upload_root / "map-emblems" / emblem_filename
            emblem_path.parent.mkdir(parents=True, exist_ok=True)
            pending_emblem.replace(emblem_path)
            final_paths.append(emblem_path)
            db_clan.map_emblem_url = f"/images/clans/map-emblems/{emblem_filename}"

        db.commit()
        db.refresh(db_clan)
        return db_clan
    except HTTPException:
        db.rollback()
        for path in final_paths:
            path.unlink(missing_ok=True)
        raise
    except IntegrityError as error:
        db.rollback()
        for path in final_paths:
            path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=409,
            detail="Название клана или выбранный цвет уже заняты. Обновите список и повторите попытку.",
        ) from error
    except Exception as error:
        db.rollback()
        for path in final_paths:
            path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail="Не удалось создать клан с выбранным оформлением",
        ) from error
    finally:
        for path in temporary_paths:
            path.unlink(missing_ok=True)
        if pending_dir.exists() and not any(pending_dir.iterdir()):
            pending_dir.rmdir()
        if avatar is not None:
            avatar.file.close()
        if map_emblem is not None:
            map_emblem.file.close()

@router.get("/my", response_model=Clan | None)
def read_my_clan(
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Получить клан текущего пользователя"""
    clan_service = ClanService()
    clan = clan_service.get_user_clan(db, current_user.id)
    if clan is None:
        return None
    
    clan_data = clan_service.get_clan(db, clan.clan_id)
    if clan_data is None:
        raise HTTPException(status_code=404, detail="Клан не найден")
    
    # Конвертируем SQLAlchemy модель в Pydantic схему
    clan_response = Clan(
        id=clan_data.id,
        name=clan_data.name,
        motto=clan_data.motto,
        description=clan_data.description,
        leader_id=clan_data.leader_id,
        avatar_url=clan_data.avatar_url,
        map_emblem_url=clan_data.map_emblem_url,
        map_color=clan_data.map_color,
        map_color_change_used=clan_data.map_color_change_used,
        level=clan_service.get_public_level(db, clan_data),
        experience=clan_data.experience,
        max_members=clan_data.max_members,
        resources=clan_data.resources or 0,
        base_influence=clan_data.base_influence or 0,
        territory_points=clan_data.territory_points or 0,
        gold=clan_data.gold or 0,
        iron=clan_data.iron or 0,
        wood=clan_data.wood or 0,
        food=clan_data.food or 0,
        mithril=clan_data.mithril or 0,
        is_admin_clan=clan_data.is_admin_clan,
        is_recruiting=clan_data.is_recruiting,
        is_deleted=clan_data.is_deleted,
        deleted_at=clan_data.deleted_at,
        preferred_patch=clan_data.preferred_patch or "all",
        next_attack_at=clan_data.next_attack_at,
        created_at=clan_data.created_at
    )
    return clan_response

@router.get("/{clan_id:int}", response_model=Clan)
def read_clan(clan_id: int, db: Session = Depends(get_db)):
    """Получить клан по ID"""
    clan_service = ClanService()
    clan = clan_service.get_clan(db, clan_id)
    if clan is None:
        raise HTTPException(status_code=404, detail="Клан не найден")
    
    # Конвертируем SQLAlchemy модель в Pydantic схему
    clan_data = Clan(
        id=clan.id,
        name=clan.name,
        motto=clan.motto,
        description=clan.description,
        leader_id=clan.leader_id,
        avatar_url=clan.avatar_url,
        map_emblem_url=clan.map_emblem_url,
        map_color=clan.map_color,
        map_color_change_used=clan.map_color_change_used,
        level=clan_service.get_public_level(db, clan),
        experience=clan.experience,
        max_members=clan.max_members,
        resources=clan.resources or 0,
        base_influence=clan.base_influence or 0,
        territory_points=clan.territory_points or 0,
        gold=clan.gold or 0,
        iron=clan.iron or 0,
        wood=clan.wood or 0,
        food=clan.food or 0,
        mithril=clan.mithril or 0,
        is_admin_clan=clan.is_admin_clan,
        is_recruiting=clan.is_recruiting,
        is_deleted=clan.is_deleted,
        deleted_at=clan.deleted_at,
        preferred_patch=clan.preferred_patch or "all",
        next_attack_at=clan.next_attack_at,
        created_at=clan.created_at
    )
    return clan_data

@router.put("/{clan_id:int}", response_model=Clan)
def update_clan(
    clan_id: int,
    clan_update: ClanUpdate,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Обновить клан"""
    clan_service = ClanService()
    
    # Проверяем, что клан существует
    clan = clan_service.get_clan(db, clan_id)
    if clan is None:
        raise HTTPException(status_code=404, detail="Клан не найден")
    
    require_clan_permission(db, clan_id, current_user, ClanPermission.MANAGE_CLAN)
    
    return clan_service.update_clan(
        db,
        clan_id,
        clan_update,
        actor=current_user,
    )

@router.get("/{clan_id:int}/members", response_model=List[ClanMemberWithUser])
def read_clan_members(
    clan_id: int,
    db: Session = Depends(get_db)
):
    """Получить участников клана"""
    clan_service = ClanService()
    
    # Проверяем, что клан существует
    clan = clan_service.get_clan(db, clan_id)
    if clan is None:
        raise HTTPException(status_code=404, detail="Клан не найден")
    
    members_data = clan_service.get_clan_members(db, clan_id)
    return [ClanMemberWithUser(**member) for member in members_data]


@router.post("/{clan_id:int}/admin-members/{user_id:int}")
def appoint_admin_clan_member(
    clan_id: int,
    user_id: int,
    current_user: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    member = ClanService().appoint_admin_clan_member(
        db,
        clan_id,
        user_id,
        current_user,
    )
    return {
        "message": "Пользователь назначен в административный клан",
        "member_id": member.id,
        "clan_id": member.clan_id,
        "user_id": member.user_id,
    }


@router.delete("/{clan_id:int}/admin-members/{user_id:int}")
def remove_admin_clan_member(
    clan_id: int,
    user_id: int,
    current_user: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    removed = ClanService().remove_admin_clan_member(
        db,
        clan_id,
        user_id,
        current_user,
    )
    if not removed:
        raise HTTPException(
            status_code=404,
            detail="Участник административного клана не найден",
        )
    return {"message": "Пользователь исключен из административного клана"}


@router.post("/{clan_id:int}/admin-sandbox/reset", response_model=Clan)
def reset_admin_clan_sandbox(
    clan_id: int,
    current_user: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    return ClanService().reset_admin_clan_sandbox(
        db,
        clan_id,
        current_user,
    )

@router.post("/{clan_id:int}/invite", response_model=ClanInvite)
def invite_to_clan(
    clan_id: int,
    invite: ClanInviteCreate,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Пригласить пользователя в клан"""
    clan_service = ClanService()
    
    # Проверяем, что клан существует
    clan = clan_service.get_clan(db, clan_id)
    if clan is None:
        raise HTTPException(status_code=404, detail="Клан не найден")
    if clan.is_admin_clan and not is_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Участников системного клана назначает только администратор",
        )
    
    require_clan_permission(db, clan_id, current_user, ClanPermission.MANAGE_MEMBERS)
    
    # Проверяем, что приглашаемый пользователь не состоит уже в клане
    target_user_clan = clan_service.get_user_clan(db, invite.invitee_id)
    if target_user_clan:
        raise HTTPException(status_code=400, detail="Пользователь уже состоит в клане")
    
    # Проверяем, разрешает ли пользователь приглашения в клан
    from app.services.user_service import UserService
    user_service = UserService()
    target_user = user_service.get_user(db, invite.invitee_id)
    if target_user and not target_user.allow_clan_invites:
        raise HTTPException(status_code=403, detail="Пользователь не принимает приглашения в клан")
    
    return clan_service.create_clan_invite(db, invite, current_user.id, clan_id)

@router.put("/invites/{invite_id:int}")
def respond_to_invite(
    invite_id: int,
    status: str,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Ответить на приглашение в клан"""
    clan_service = ClanService()
    
    if status not in ["accepted", "declined"]:
        raise HTTPException(status_code=400, detail="Статус должен быть 'accepted' или 'declined'")
    
    result = clan_service.respond_to_invite(db, invite_id, current_user.id, status)
    if not result:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")
    
    return {"message": f"Приглашение {status}"}

@router.get("/invites/", response_model=List[ClanInviteWithDetails])
def read_user_invites(
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Получить приглашения пользователя"""
    print(f"Getting invites for user: {current_user.id} ({current_user.username})")
    clan_service = ClanService()
    invites = clan_service.get_user_invites(db, current_user.id)
    print(f"Found {len(invites)} invites")
    return invites

@router.post("/{clan_id:int}/applications", response_model=ClanApplication)
def create_application(
    clan_id: int,
    application: ClanApplicationCreate,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Подать заявку в клан"""
    clan_service = ClanService()
    
    # Проверяем, что клан существует
    clan = clan_service.get_clan(db, clan_id)
    if clan is None:
        raise HTTPException(status_code=404, detail="Клан не найден")
    if clan.is_admin_clan:
        raise HTTPException(
            status_code=403,
            detail="Системный клан нельзя удалить",
        )
    
    db_application = clan_service.create_clan_application(db, clan_id, application, current_user.id)
    if not db_application:
        raise HTTPException(status_code=400, detail="Заявка уже существует")
    
    return db_application

@router.get("/{clan_id:int}/applications", response_model=List[ClanApplicationWithDetails])
def get_applications(
    clan_id: int,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Получить заявки в клан"""
    clan_service = ClanService()
    
    # Проверяем, что пользователь является лидером клана
    clan = clan_service.get_clan(db, clan_id)
    if clan is None:
        raise HTTPException(status_code=404, detail="Клан не найден")
    
    require_clan_permission(db, clan_id, current_user, ClanPermission.MANAGE_MEMBERS)
    
    return clan_service.get_pending_applications(db, clan_id)

@router.delete("/{clan_id:int}")
def delete_clan(
    clan_id: int,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Удалить клан"""
    clan_service = ClanService()
    
    # Проверяем, что клан существует
    clan = clan_service.get_clan(db, clan_id)
    if clan is None:
        raise HTTPException(status_code=404, detail="Клан не найден")
    
    require_clan_permission(db, clan_id, current_user, ClanPermission.MANAGE_CLAN)
    
    clan_service.delete_clan(db, clan_id)
    return {"message": "Клан успешно удален"}

@router.post("/{clan_id:int}/leave")
def leave_clan(
    clan_id: int,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Покинуть клан"""
    clan_service = ClanService()
    
    # Проверяем, что пользователь состоит в клане
    user_clan = clan_service.get_user_clan(db, current_user.id)
    if not user_clan or user_clan.clan_id != clan_id:
        raise HTTPException(status_code=404, detail="Пользователь не состоит в этом клане")
    
    # Проверяем, что пользователь не является лидером
    clan = clan_service.get_clan(db, clan_id)
    if clan.leader_id == current_user.id:
        raise HTTPException(status_code=400, detail="Лидер клана не может покинуть клан. Передайте лидерство или удалите клан")
    
    clan_service.leave_clan(db, current_user.id)
    return {"message": "Вы покинули клан"}

@router.delete("/{clan_id:int}/members/{user_id:int}")
def kick_member(
    clan_id: int,
    user_id: int,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Исключить участника из клана"""
    clan_service = ClanService()
    clan = clan_service.get_clan(db, clan_id)
    if clan is None:
        raise HTTPException(status_code=404, detail="Клан не найден")
    if clan.is_admin_clan and not is_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Участников системного клана назначает только администратор",
        )
    
    require_clan_permission(db, clan_id, current_user, ClanPermission.MANAGE_MEMBERS)
    
    # Проверяем, что пользователь не пытается исключить сам себя
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Лидер не может исключить сам себя")
    
    success = clan_service.kick_member(db, clan_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Участник не найден в клане")
    
    return {"message": "Участник исключен из клана"}

@router.post("/{clan_id:int}/avatar")
def upload_clan_avatar(
    clan_id: int,
    avatar: UploadFile = File(...),
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Загрузить аватар клана"""
    clan_service = ClanService()
    clan = clan_service.get_clan(db, clan_id)
    if clan is None:
        raise HTTPException(status_code=404, detail="Клан не найден")
    previous_avatar_url = clan.avatar_url
    
    require_clan_permission(db, clan_id, current_user, ClanPermission.MANAGE_CLAN)
    
    # Проверяем тип файла
    if not avatar.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Файл должен быть изображением")
    
    # Проверяем размер файла (максимум 5MB)
    if avatar.size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Размер файла не должен превышать 5MB")
    
    try:
        # Обрабатываем изображение
        image_data = avatar.file.read()
        
        # Генерируем уникальное имя файла
        file_extension = os.path.splitext(avatar.filename)[1]
        filename = f"clan_{clan_id}_{uuid.uuid4().hex}{file_extension}"
        
        # Сохраняем файл
        upload_dir = os.path.join(settings.UPLOAD_DIR, "clans")
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, filename)
        
        # Обрабатываем изображение
        process_avatar_image(image_data, file_path)
        
        # Обновляем URL аватара в базе данных
        avatar_url = f"/images/clans/{filename}"
        clan_service.update_clan_avatar(db, clan_id, avatar_url)
        remove_map_emblem_preview(previous_avatar_url)
        
        return {"avatar_url": avatar_url, "message": "Аватар клана успешно обновлен"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке аватара: {str(e)}")
    finally:
        avatar.file.close()

@router.post("/{clan_id:int}/transfer-leadership")
def transfer_leadership(
    clan_id: int,
    request: TransferLeadershipRequest,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Передать лидерство клана"""
    clan_service = ClanService()
    
    # Проверяем, что клан существует
    clan = clan_service.get_clan(db, clan_id)
    if clan is None:
        raise HTTPException(status_code=404, detail="Клан не найден")
    if clan.is_admin_clan and not is_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Главу системного клана назначает только администратор",
        )
    
    require_clan_permission(db, clan_id, current_user, ClanPermission.MANAGE_ROLES)
    
    # Проверяем, что новый лидер состоит в клане
    user_clan = clan_service.get_user_clan(db, request.user_id)
    if not user_clan or user_clan.clan_id != clan_id:
        raise HTTPException(status_code=404, detail="Пользователь не состоит в этом клане")
    target_user = db.query(UserModel).filter(UserModel.id == request.user_id).first()
    if clan.is_admin_clan and (not target_user or not is_admin(target_user)):
        raise HTTPException(
            status_code=403,
            detail="Главой системного клана может быть только администратор",
        )
    
    clan_service.transfer_leadership(db, clan_id, request.user_id)
    return {"message": "Лидерство передано"}

@router.put("/applications/{application_id:int}")
def respond_to_application(
    application_id: int,
    status: str,
    current_user: UserModel = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db)
):
    """Ответить на заявку в клан"""
    clan_service = ClanService()
    
    if status not in ["accepted", "declined"]:
        raise HTTPException(status_code=400, detail="Статус должен быть 'accepted' или 'declined'")
    
    result = clan_service.respond_to_application(db, application_id, current_user, status)
    if not result:
        raise HTTPException(status_code=404, detail="Заявка не найдена или у вас нет прав для её обработки")
    
    return {"message": f"Заявка {status}"} 
