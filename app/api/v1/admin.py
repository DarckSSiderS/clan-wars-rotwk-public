import os
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.auth import get_current_admin_user
from app.core.admin_policy import is_primary_admin
from app.core.time import utc_now
from app.database import get_db
from app.models.campaign import CampaignSeason, ReplaySyncState
from app.models.clan import Clan, ClanMember
from app.models.market import TradeCaravan
from app.models.match import Match
from app.models.operation import AdminAuditLog, ResourceLedgerEntry
from app.models.role import Role
from app.models.territory import Territory
from app.models.title import Title, UserTitle
from app.models.user import User
from app.models.war import ClanWar, ClanWarMatchResult
from app.models.worker import WorkerHeartbeat
from app.services.operation_service import AdminAuditService, ResourceLedgerService
from app.services.clan_influence_service import ClanInfluenceService
from app.services.territory_ownership_service import TerritoryOwnershipService
from app.services.war_service import ClanWarService
from app.services.admin_identity_binding_service import AdminIdentityBindingService
from app.config import settings
from app.utils.image_processor import process_title_image


router = APIRouter(prefix="/admin", tags=["admin"])

RESOURCE_FIELDS = ("gold", "iron", "wood", "food", "mithril", "influence")
TERRITORY_EDIT_FIELDS = (
    "owner_clan_id",
    "resource_wealth",
    "resource_type",
    "resource_output",
    "secondary_resource_type",
    "population",
    "influence_value",
    "required_influence",
    "development_level",
    "fortifications",
    "offense_level",
    "is_playable",
    "is_coastal",
    "has_port",
    "port_level",
    "fleet_level",
    "required_territories",
    "stronghold_power",
)


class ClanEconomyUpdate(BaseModel):
    gold: int | None = Field(None, ge=0, le=100_000_000)
    iron: int | None = Field(None, ge=0, le=10_000_000)
    wood: int | None = Field(None, ge=0, le=10_000_000)
    food: int | None = Field(None, ge=0, le=10_000_000)
    mithril: int | None = Field(None, ge=0, le=10_000_000)
    influence: int | None = Field(None, ge=0, le=100_000_000)
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_changes(self):
        if not any(getattr(self, field) is not None for field in RESOURCE_FIELDS):
            raise ValueError("Укажите хотя бы одно изменяемое значение")
        self.reason = self.reason.strip()
        return self


class AdminReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def normalize_reason(self):
        self.reason = self.reason.strip()
        if len(self.reason) < 3:
            raise ValueError("Причина должна содержать не меньше трёх символов")
        return self


class AdminPermanentDeleteRequest(AdminReasonRequest):
    confirmation_id: int


class WarScoreAdjustmentRequest(AdminReasonRequest):
    clan_id: int
    points: float = Field(ge=-1000000, le=1000000, allow_inf_nan=False)
    request_id: UUID


@router.post("/wars/{war_id}/points")
def adjust_war_points(war_id: int, request: WarScoreAdjustmentRequest,
    current_admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    from app.models.war_adjustment import WarScoreAdjustment
    war = db.query(ClanWar).filter_by(id=war_id).with_for_update().first()
    if war is None:
        raise HTTPException(404, "Битва не найдена")
    if request.clan_id not in {war.attacking_clan_id, war.defending_clan_id} or request.points == 0:
        raise HTTPException(422, "Выберите сторону битвы и ненулевое количество очков")
    prior = db.query(WarScoreAdjustment).filter_by(request_id=str(request.request_id)).first()
    if prior:
        if (prior.war_id, prior.clan_id, prior.points, prior.actor_id) != (war_id, request.clan_id, request.points, current_admin.id):
            raise HTTPException(409, "Идентификатор операции уже использован")
        return ClanWarService().serialize_war(db, war)
    db.add(WarScoreAdjustment(war_id=war_id, clan_id=request.clan_id,
        points=request.points, actor_id=current_admin.id, reason=request.reason,
        request_id=str(request.request_id)))
    AdminAuditService().record(db, actor_user_id=current_admin.id, action="war_points_adjusted",
        entity_type="clan_war", entity_id=war_id,
        after_data={"clan_id": request.clan_id, "points": request.points}, reason=request.reason)
    db.commit()
    return ClanWarService().serialize_war(db, war)


@router.delete("/wars/{war_id}")
def permanently_delete_war(
    war_id: int,
    request: AdminPermanentDeleteRequest,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    from app.services.admin_deletion_service import AdminDeletionService
    if request.confirmation_id != war_id:
        raise HTTPException(422, "Подтвердите ID битвы")
    AdminDeletionService().delete_war(db, war_id)
    AdminAuditService().record(db, actor_user_id=current_admin.id,
        action="war_permanently_deleted", entity_type="clan_war", entity_id=war_id,
        before_data=None, after_data=None, reason=request.reason)
    db.commit()
    return {"deleted": True}


@router.delete("/clans/{clan_id}")
def permanently_delete_clan(
    clan_id: int,
    request: AdminPermanentDeleteRequest,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    from app.services.admin_deletion_service import AdminDeletionService
    if request.confirmation_id != clan_id:
        raise HTTPException(422, "Подтвердите ID клана")
    AdminDeletionService().delete_clan(db, clan_id)
    AdminAuditService().record(db, actor_user_id=current_admin.id,
        action="clan_permanently_deleted", entity_type="clan", entity_id=clan_id,
        before_data=None, after_data=None, reason=request.reason)
    db.commit()
    return {"deleted": True}


class AdminUserRoleUpdate(AdminReasonRequest):
    is_admin: bool


class AdminArenaIdentityUpdate(AdminReasonRequest):
    arena_nickname: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def normalize_nickname(self):
        self.arena_nickname = self.arena_nickname.strip()
        if not self.arena_nickname:
            raise ValueError("Укажите ник BFME Arena")
        return self


class WarExtensionRequest(AdminReasonRequest):
    hours: int = Field(ge=1, le=168)


class WarFinishRequest(AdminReasonRequest):
    winner_clan_id: int = Field(ge=1)


class WarMatchReviewRequest(AdminReasonRequest):
    mode: Literal["count", "exclude", "automatic"]


class AdminTerritoryUpdate(AdminReasonRequest):
    owner_clan_id: int | None = Field(None, ge=1)
    resource_wealth: int | None = Field(None, ge=0, le=10_000_000)
    resource_type: Literal["gold", "iron", "wood", "food", "mithril"] | None = None
    resource_output: int | None = Field(None, ge=0, le=1000)
    secondary_resource_type: Literal["gold", "iron", "wood", "food", "mithril"] | None = None
    population: int | None = Field(None, ge=0, le=100_000_000)
    influence_value: int | None = Field(None, ge=0, le=10_000_000)
    required_influence: int | None = Field(None, ge=0, le=100_000_000)
    development_level: int | None = Field(None, ge=0, le=10)
    fortifications: int | None = Field(None, ge=0, le=10)
    offense_level: int | None = Field(None, ge=0, le=10)
    is_playable: bool | None = None
    is_coastal: bool | None = None
    has_port: bool | None = None
    port_level: int | None = Field(None, ge=0, le=10)
    fleet_level: int | None = Field(None, ge=0, le=10)
    required_territories: int | None = Field(None, ge=0, le=76)
    stronghold_power: int | None = Field(None, ge=0, le=10)

    @model_validator(mode="after")
    def validate_territory_changes(self):
        if not any(field in self.model_fields_set for field in TERRITORY_EDIT_FIELDS):
            raise ValueError("Укажите хотя бы один изменяемый параметр территории")
        if (
            self.resource_type is not None
            and self.secondary_resource_type is not None
            and self.resource_type == self.secondary_resource_type
        ):
            raise ValueError("Основной и второй ресурсы должны отличаться")
        return self


def _clan_economy(clan: Clan) -> dict:
    return {
        "gold": int(clan.gold or 0),
        "iron": int(clan.iron or 0),
        "wood": int(clan.wood or 0),
        "food": int(clan.food or 0),
        "mithril": int(clan.mithril or 0),
        "influence": int(clan.territory_points or 0),
    }


def _title_payload(title: Title) -> dict:
    return {
        "id": title.id,
        "name": title.name,
        "description": title.description,
        "name_en": title.name_en,
        "description_en": title.description_en,
        "name_de": title.name_de,
        "description_de": title.description_de,
        "image_url": title.image_url,
        "is_active": bool(title.is_active),
        "created_at": title.created_at.isoformat() if title.created_at else None,
        "updated_at": title.updated_at.isoformat() if title.updated_at else None,
    }


async def _save_title_image(image: UploadFile) -> str:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Файл титула должен быть изображением")
    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл титула пуст")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Размер изображения не должен превышать 5 МБ")

    upload_dir = os.path.join(settings.UPLOAD_DIR, "titles")
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"title_{uuid4().hex}.webp"
    file_path = os.path.join(upload_dir, filename)
    try:
        process_title_image(content, file_path)
    except Exception as error:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail="Не удалось обработать изображение титула") from error
    return f"/images/titles/{filename}"


def _war_audit_state(war: ClanWar) -> dict:
    return {
        "status": war.status,
        "winner_clan_id": war.winner_clan_id,
        "ends_at": war.ends_at.isoformat() if war.ends_at else None,
        "ended_at": war.ended_at.isoformat() if war.ended_at else None,
        "territory_owner_clan_id": (
            war.territory.owner_clan_id if war.territory else None
        ),
        "attacker_next_attack_at": (
            war.attacking_clan.next_attack_at.isoformat()
            if war.attacking_clan and war.attacking_clan.next_attack_at else None
        ),
    }


def _admin_territory_payload(
    db: Session,
    territory: Territory,
    active_territory_ids: set[int] | None = None,
) -> dict:
    has_active_war = (
        territory.id in active_territory_ids
        if active_territory_ids is not None
        else bool(db.query(ClanWar.id).filter(
            ClanWar.territory_id == territory.id,
            ClanWar.status == "active",
        ).first())
    )
    return {
        "id": territory.id,
        "name": territory.name,
        "region": territory.region,
        "owner_clan_id": territory.owner_clan_id,
        "owner_clan_name": territory.owner_clan.name if territory.owner_clan else None,
        "status": territory.status,
        "has_active_war": has_active_war,
        "resource_wealth": int(territory.resource_wealth or 0),
        "daily_income": float(territory.daily_income),
        "weekly_income": float(territory.weekly_income),
        "resource_type": territory.resource_type or "iron",
        "resource_output": int(territory.resource_output or 0),
        "secondary_resource_type": territory.secondary_resource_type,
        "population": int(territory.population or 0),
        "influence_value": int(territory.influence_value or 0),
        "required_influence": int(territory.required_influence or 0),
        "development_level": int(territory.development_level or 0),
        "fortifications": int(territory.fortifications or 0),
        "offense_level": int(territory.offense_level or 0),
        "strategic_value": float(territory.strategic_value or 0),
        "is_playable": territory.is_playable is not False,
        "is_coastal": bool(territory.is_coastal),
        "has_port": bool(territory.has_port),
        "port_level": int(territory.port_level or 0),
        "fleet_level": int(territory.fleet_level or 0),
        "required_territories": int(territory.required_territories or 0),
        "stronghold_power": int(territory.stronghold_power or 0),
        "updated_at": territory.updated_at,
    }


@router.get("/overview")
def get_admin_overview(
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    worker = db.query(WorkerHeartbeat).order_by(WorkerHeartbeat.heartbeat_at.desc()).first()
    active_season = db.query(CampaignSeason).filter(CampaignSeason.status == "active").first()
    return {
        "users": {
            "registered": db.query(User).filter(User.is_claimed.is_(True)).count(),
            "active": db.query(User).filter(User.is_claimed.is_(True), User.is_active.is_(True)).count(),
            "blocked": db.query(User).filter(User.is_claimed.is_(True), User.is_active.is_(False)).count(),
        },
        "clans": {
            "total": db.query(Clan).filter(
                Clan.is_admin_clan.is_(False),
                Clan.is_deleted.is_(False),
            ).count(),
            "members": db.query(ClanMember).count(),
        },
        "campaign": {
            "territories": db.query(Territory).count(),
            "owned_territories": db.query(Territory).filter(Territory.owner_clan_id.isnot(None)).count(),
            "active_wars": db.query(ClanWar).filter(ClanWar.status == "active").count(),
            "active_caravans": db.query(TradeCaravan).filter(TradeCaravan.status == "traveling").count(),
            "season": {
                "id": active_season.id,
                "name": active_season.name,
                "started_at": active_season.starts_at,
            } if active_season else None,
        },
        "matches": {
            "total": db.query(Match).count(),
            "sync_errors": db.query(ReplaySyncState).filter(ReplaySyncState.status == "error").count(),
        },
        "worker": {
            "name": worker.worker_name,
            "heartbeat_at": worker.heartbeat_at,
            "last_success_at": worker.last_success_at,
            "last_error_at": worker.last_error_at,
            "last_error": worker.last_error,
            "consecutive_failures": int(worker.consecutive_failures or 0),
            "last_notification_at": worker.last_notification_at,
            "notifications_configured": bool(settings.WORKER_ALERT_WEBHOOK_URL),
        } if worker else None,
    }


@router.get("/users")
def get_admin_users(
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    search: str | None = None,
    title_filter: Literal["all", "with", "without"] = "all",
    title_id: int | None = None,
    limit: int | None = None,
):
    clean_search = (search or "").strip()
    if len(clean_search) > 120:
        raise HTTPException(status_code=422, detail="Поисковый запрос слишком длинный")
    if limit is not None and (limit < 1 or limit > 100):
        raise HTTPException(status_code=422, detail="Лимит должен быть от 1 до 100")

    query = db.query(User).options(
        joinedload(User.role),
        selectinload(User.title_assignments).joinedload(UserTitle.title),
    )
    if clean_search:
        query = query.filter(
            func.lower(User.username).contains(clean_search.lower(), autoescape=True)
        )

    assignment_filter = User.title_assignments.any()
    if title_id is not None:
        assignment_filter = User.title_assignments.any(UserTitle.title_id == title_id)
    if title_filter == "with":
        query = query.filter(assignment_filter)
    elif title_filter == "without":
        query = query.filter(~assignment_filter)

    query = query.order_by(User.is_claimed.desc(), User.username.asc())
    if limit is not None:
        query = query.limit(limit)
    users = query.all()
    return {
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name or user.username,
                "is_active": bool(user.is_active),
                "is_claimed": bool(user.is_claimed),
                "is_admin": bool(user.role and user.role.name == "admin"),
                "role": user.role.name if user.role else None,
                "titles": [
                    _title_payload(assignment.title)
                    for assignment in user.title_assignments
                    if assignment.title
                ],
                "created_at": user.created_at,
            }
            for user in users
        ]
    }


@router.get("/titles")
def get_admin_titles(
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    titles = db.query(Title).order_by(Title.name.asc()).all()
    assignment_counts = dict(
        db.query(UserTitle.title_id, func.count(UserTitle.id))
        .group_by(UserTitle.title_id)
        .all()
    )
    return {
        "titles": [
            {**_title_payload(title), "assigned_count": int(assignment_counts.get(title.id, 0))}
            for title in titles
        ]
    }


@router.post("/titles")
async def create_admin_title(
    name: str = Form(...),
    description: str = Form(...),
    name_en: str | None = Form(None),
    description_en: str | None = Form(None),
    name_de: str | None = Form(None),
    description_de: str | None = Form(None),
    image: UploadFile = File(...),
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    clean_name = name.strip()
    clean_description = description.strip()
    if len(clean_name) < 2 or len(clean_name) > 120:
        raise HTTPException(status_code=400, detail="Название титула должно содержать от 2 до 120 символов")
    if len(clean_description) < 3 or len(clean_description) > 1000:
        raise HTTPException(status_code=400, detail="Описание титула должно содержать от 3 до 1000 символов")
    if db.query(Title.id).filter(func.lower(Title.name) == clean_name.lower()).first():
        raise HTTPException(status_code=409, detail="Титул с таким названием уже существует")

    image_url = await _save_title_image(image)
    title = Title(
        name=clean_name,
        description=clean_description,
        name_en=(name_en or "").strip() or None,
        description_en=(description_en or "").strip() or None,
        name_de=(name_de or "").strip() or None,
        description_de=(description_de or "").strip() or None,
        image_url=image_url,
    )
    db.add(title)
    db.flush()
    AdminAuditService().record(
        db,
        actor_user_id=current_admin.id,
        action="title_created",
        entity_type="title",
        entity_id=title.id,
        after_data=_title_payload(title),
        reason="Создание титула",
    )
    db.commit()
    db.refresh(title)
    return _title_payload(title)


@router.patch("/titles/{title_id:int}")
async def update_admin_title(
    title_id: int,
    name: str | None = Form(None),
    description: str | None = Form(None),
    name_en: str | None = Form(None),
    description_en: str | None = Form(None),
    name_de: str | None = Form(None),
    description_de: str | None = Form(None),
    is_active: bool | None = Form(None),
    image: UploadFile | None = File(None),
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    title = db.query(Title).filter(Title.id == title_id).with_for_update().first()
    if title is None:
        raise HTTPException(status_code=404, detail="Титул не найден")

    before = _title_payload(title)
    if name is not None:
        clean_name = name.strip()
        if len(clean_name) < 2 or len(clean_name) > 120:
            raise HTTPException(status_code=400, detail="Название титула должно содержать от 2 до 120 символов")
        duplicate = db.query(Title.id).filter(
            Title.id != title.id,
            func.lower(Title.name) == clean_name.lower(),
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Титул с таким названием уже существует")
        title.name = clean_name
    if description is not None:
        clean_description = description.strip()
        if len(clean_description) < 3 or len(clean_description) > 1000:
            raise HTTPException(status_code=400, detail="Описание титула должно содержать от 3 до 1000 символов")
        title.description = clean_description
    for field, value in (
        ("name_en", name_en),
        ("description_en", description_en),
        ("name_de", name_de),
        ("description_de", description_de),
    ):
        if value is not None:
            setattr(title, field, value.strip() or None)
    if is_active is not None:
        title.is_active = is_active
    if image is not None:
        title.image_url = await _save_title_image(image)

    AdminAuditService().record(
        db,
        actor_user_id=current_admin.id,
        action="title_updated",
        entity_type="title",
        entity_id=title.id,
        before_data=before,
        after_data=_title_payload(title),
        reason="Изменение титула",
    )
    db.commit()
    db.refresh(title)
    return _title_payload(title)


@router.post("/titles/{title_id:int}/users/{user_id:int}")
def assign_admin_title(
    title_id: int,
    user_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    title = db.query(Title).filter(Title.id == title_id).first()
    user = db.query(User).filter(User.id == user_id).first()
    if title is None:
        raise HTTPException(status_code=404, detail="Титул не найден")
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if not title.is_active:
        raise HTTPException(status_code=400, detail="Нельзя назначить отключенный титул")
    existing = db.query(UserTitle).filter_by(user_id=user.id, title_id=title.id).first()
    if existing:
        return {"assigned": True, "user_id": user.id, "title": _title_payload(title)}

    assignment = UserTitle(
        user_id=user.id,
        title_id=title.id,
        assigned_by_user_id=current_admin.id,
    )
    db.add(assignment)
    AdminAuditService().record(
        db,
        actor_user_id=current_admin.id,
        action="title_assigned",
        entity_type="user",
        entity_id=user.id,
        after_data={"username": user.username, "title": title.name, "title_id": title.id},
        reason="Назначение титула",
    )
    db.commit()
    return {"assigned": True, "user_id": user.id, "title": _title_payload(title)}


@router.delete("/titles/{title_id:int}/users/{user_id:int}")
def remove_admin_title(
    title_id: int,
    user_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    assignment = db.query(UserTitle).filter_by(user_id=user_id, title_id=title_id).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Этот титул пользователю не назначен")
    title = assignment.title
    user = assignment.user
    db.delete(assignment)
    AdminAuditService().record(
        db,
        actor_user_id=current_admin.id,
        action="title_removed",
        entity_type="user",
        entity_id=user.id,
        before_data={"username": user.username, "title": title.name, "title_id": title.id},
        reason="Снятие титула",
    )
    db.commit()
    return {"assigned": False, "user_id": user.id, "title_id": title_id}


@router.patch("/users/{user_id:int}/role")
def update_admin_user_role(
    user_id: int,
    request: AdminUserRoleUpdate,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    target = (
        db.query(User)
        .filter(User.id == user_id)
        .with_for_update()
        .first()
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if request.is_admin and not target.is_claimed:
        raise HTTPException(
            status_code=400,
            detail="Нельзя выдать права непривязанному игровому профилю",
        )
    if is_primary_admin(target.username) and not request.is_admin:
        raise HTTPException(
            status_code=400,
            detail="Нельзя снять права с главного администратора darcks",
        )
    if target.id == current_admin.id and not request.is_admin:
        raise HTTPException(
            status_code=400,
            detail="Нельзя снять права администратора с текущего аккаунта",
        )

    role_name = "admin" if request.is_admin else "user"
    role = db.query(Role).filter(Role.name == role_name).first()
    if role is None:
        raise HTTPException(
            status_code=500,
            detail=f"Системная роль {role_name} не настроена",
        )

    before_role = target.role.name if target.role else None
    target.role = role
    AdminAuditService().record(
        db,
        actor_user_id=current_admin.id,
        action="user_admin_role_updated",
        entity_type="user",
        entity_id=target.id,
        before_data={"username": target.username, "role": before_role},
        after_data={"username": target.username, "role": role_name},
        reason=request.reason,
    )
    db.commit()
    return {
        "id": target.id,
        "username": target.username,
        "is_admin": request.is_admin,
        "role": role_name,
    }


@router.patch("/users/{user_id:int}/arena-identity")
def update_admin_arena_identity(
    user_id: int,
    request: AdminArenaIdentityUpdate,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    try:
        identity = AdminIdentityBindingService().bind(
            db,
            target_user=target,
            arena_nickname=request.arena_nickname,
            actor=current_admin,
            reason=request.reason,
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error

    db.refresh(target)
    return {
        "id": target.id,
        "username": target.username,
        "display_name": target.display_name or target.username,
        "arena_nickname": identity.current_nickname,
        "external_uuid": identity.external_uuid,
        "verification_status": identity.verification_status,
    }


@router.get("/clans")
def get_admin_clans(
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    member_count = (
        db.query(ClanMember.clan_id, func.count(ClanMember.id).label("count"))
        .group_by(ClanMember.clan_id)
        .subquery()
    )
    territory_count = (
        db.query(Territory.owner_clan_id.label("clan_id"), func.count(Territory.id).label("count"))
        .filter(Territory.owner_clan_id.isnot(None))
        .group_by(Territory.owner_clan_id)
        .subquery()
    )
    rows = (
        db.query(Clan, member_count.c.count, territory_count.c.count)
        .outerjoin(member_count, member_count.c.clan_id == Clan.id)
        .outerjoin(territory_count, territory_count.c.clan_id == Clan.id)
        .order_by(Clan.is_admin_clan.desc(), Clan.name.asc())
        .all()
    )
    from app.models.cycle_economy import CycleEconomyState
    from app.services.cycle_economy import RESOURCE_NAMES
    season = db.query(CampaignSeason).filter_by(status='active').order_by(CampaignSeason.number.desc()).first()
    if season is None:
        season = db.query(CampaignSeason).order_by(CampaignSeason.number.desc()).first()
    cycle_mode = bool(season and (season.rules_snapshot or {}).get('mechanics_version') == 'cycle_v1')
    wallets = {state.clan_id: state.wallet for state in db.query(CycleEconomyState).filter_by(season_id=season.id)} if cycle_mode else {}
    return {
        "clans": [
            {
                "id": clan.id,
                "name": clan.name,
                "is_admin_clan": clan.is_admin_clan,
                "members": int(members or 0),
                "territories": int(territories or 0),
                **_clan_economy(clan),
                **({key: wallets.get(clan.id, {}).get(key) for key in RESOURCE_NAMES} if cycle_mode else {}),
            }
            for clan, members, territories in rows
        ]
    }


@router.patch("/clans/{clan_id}/economy")
def update_clan_economy(
    clan_id: int,
    request: ClanEconomyUpdate,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    from app.core.campaign_mode import cycle_owns_campaign
    if cycle_owns_campaign(db):
        raise HTTPException(status_code=409, detail='В новой кампании изменяйте сезонную казну; обновите страницу управления')
    clan = db.query(Clan).filter(Clan.id == clan_id).with_for_update().first()
    if not clan:
        raise HTTPException(status_code=404, detail="Клан не найден")

    before = _clan_economy(clan)
    requested = request.model_dump(exclude={"reason"}, exclude_none=True)
    operation_id = f"admin-clan-economy:{current_admin.id}:{clan.id}:{uuid4().hex}"
    ledger = ResourceLedgerService()

    try:
        for resource, target in requested.items():
            delta = int(target) - before[resource]
            if delta == 0:
                continue
            ledger.apply_change(
                db,
                clan,
                resource=resource,
                amount=delta,
                operation_id=operation_id,
                action="admin_adjustment",
                source_type="admin_panel",
                source_id=clan.id,
                actor_user_id=current_admin.id,
                details={"reason": request.reason, "target_value": int(target)},
            )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    after = _clan_economy(clan)
    if before == after:
        raise HTTPException(status_code=409, detail="Значения не изменились")

    AdminAuditService().record(
        db,
        actor_user_id=current_admin.id,
        action="clan_economy_updated",
        entity_type="clan",
        entity_id=clan.id,
        before_data=before,
        after_data=after,
        reason=request.reason,
    )
    db.commit()
    db.refresh(clan)
    return {"clan": {"id": clan.id, "name": clan.name, **_clan_economy(clan)}}


@router.get("/territories")
def get_admin_territories(
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    territories = (
        db.query(Territory)
        .options(joinedload(Territory.owner_clan))
        .order_by(Territory.region, Territory.name)
        .all()
    )
    active_territory_ids = {
        territory_id
        for territory_id, in db.query(ClanWar.territory_id).filter(
            ClanWar.status == "active",
        ).distinct().all()
    }
    return {
        "territories": [
            _admin_territory_payload(db, territory, active_territory_ids)
            for territory in territories
        ]
    }


@router.patch("/territories/{territory_id}")
def update_admin_territory(
    territory_id: int,
    request: AdminTerritoryUpdate,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    territory = (
        db.query(Territory)
        .filter(Territory.id == territory_id)
        .with_for_update()
        .first()
    )
    if not territory:
        raise HTTPException(status_code=404, detail="Территория не найдена")

    requested = request.model_dump(exclude={"reason"}, exclude_unset=True)
    owner_was_requested = "owner_clan_id" in requested
    new_owner_clan_id = requested.pop("owner_clan_id", territory.owner_clan_id)
    owner_changed = owner_was_requested and new_owner_clan_id != territory.owner_clan_id
    if owner_changed:
        if db.query(ClanWar.id).filter(
            ClanWar.territory_id == territory.id,
            ClanWar.status == "active",
        ).first():
            raise HTTPException(
                status_code=409,
                detail="Сначала завершите или отмените активную войну за эту территорию",
            )
        if new_owner_clan_id is not None and not db.query(Clan.id).filter(
            Clan.id == new_owner_clan_id,
        ).first():
            raise HTTPException(status_code=404, detail="Новый клан-владелец не найден")

    before = {
        field: getattr(territory, field)
        for field in TERRITORY_EDIT_FIELDS
    }
    effective_resource_type = requested.get("resource_type", territory.resource_type or "iron")
    effective_stronghold = requested.get("stronghold_power", territory.stronghold_power or 0)
    effective_secondary = requested.get(
        "secondary_resource_type",
        territory.secondary_resource_type,
    )
    if effective_stronghold > 0:
        if not effective_secondary:
            raise HTTPException(
                status_code=400,
                detail="Для великой крепости выберите второй редкий ресурс",
            )
        if effective_secondary == effective_resource_type:
            raise HTTPException(
                status_code=400,
                detail="Основной и второй ресурсы великой крепости должны отличаться",
            )
    else:
        requested["secondary_resource_type"] = None

    effective_has_port = requested.get("has_port", territory.has_port)
    effective_port_level = requested.get("port_level", territory.port_level or 0)
    effective_fleet_level = requested.get("fleet_level", territory.fleet_level or 0)
    if not effective_has_port:
        requested["port_level"] = 0
        requested["fleet_level"] = 0
    elif effective_fleet_level > effective_port_level:
        raise HTTPException(
            status_code=400,
            detail="Уровень флота не может быть выше уровня порта",
        )

    influence_changed = (
        "influence_value" in requested
        and requested["influence_value"] != territory.influence_value
    )
    for field, value in requested.items():
        setattr(territory, field, value)
    territory.strategic_value = territory.calculate_strategic_value()

    if owner_changed:
        TerritoryOwnershipService().transfer(
            db,
            territory,
            new_owner_clan_id,
            reason="admin_update",
            actor_user_id=current_admin.id,
            details={"reason": request.reason},
        )
        territory.status = "active" if new_owner_clan_id else "neutral"
    elif influence_changed and territory.owner_clan_id:
        ClanInfluenceService().recalculate(
            db,
            territory.owner_clan_id,
            operation_id=f"admin-territory:{current_admin.id}:{territory.id}:{uuid4().hex}",
            action="territory_influence_admin_update",
            source_type="territory",
            source_id=territory.id,
            actor_user_id=current_admin.id,
            details={"territory_name": territory.name, "reason": request.reason},
        )

    after = {
        field: getattr(territory, field)
        for field in TERRITORY_EDIT_FIELDS
    }
    if before == after:
        raise HTTPException(status_code=409, detail="Параметры территории не изменились")

    AdminAuditService().record(
        db,
        actor_user_id=current_admin.id,
        action="territory_parameters_updated",
        entity_type="territory",
        entity_id=territory.id,
        before_data=before,
        after_data=after,
        reason=request.reason,
    )
    db.commit()
    db.refresh(territory)
    return {"territory": _admin_territory_payload(db, territory)}


@router.get("/wars")
def get_admin_wars(
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=300),
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    if status and status not in {"active", "completed", "canceled"}:
        raise HTTPException(status_code=400, detail="Неизвестный статус войны")

    query = db.query(ClanWar)
    if status:
        query = query.filter(ClanWar.status == status)
    wars = query.order_by(ClanWar.started_at.desc(), ClanWar.id.desc()).limit(limit).all()
    war_ids = [war.id for war in wars]
    counts = {}
    if war_ids:
        count_rows = (
            db.query(
                ClanWarMatchResult.war_id,
                func.count(ClanWarMatchResult.id),
                func.sum(case((ClanWarMatchResult.is_counted.is_(True), 1), else_=0)),
            )
            .filter(ClanWarMatchResult.war_id.in_(war_ids))
            .group_by(ClanWarMatchResult.war_id)
            .all()
        )
        counts = {
            war_id: {"total": int(total or 0), "counted": int(counted or 0)}
            for war_id, total, counted in count_rows
        }

    return {
        "wars": [
            {
                "id": war.id,
                "territory_id": war.territory_id,
                "territory_name": war.territory.name if war.territory else f"Территория #{war.territory_id}",
                "attacking_clan_id": war.attacking_clan_id,
                "attacking_clan_name": war.attacking_clan.name if war.attacking_clan else f"Клан #{war.attacking_clan_id}",
                "defending_clan_id": war.defending_clan_id,
                "defending_clan_name": war.defending_clan.name if war.defending_clan else None,
                "winner_clan_id": war.winner_clan_id,
                "winner_clan_name": war.winner_clan.name if war.winner_clan else None,
                "status": war.status,
                "war_type": war.war_type,
                "attack_route": war.attack_route,
                "started_at": war.started_at,
                "ends_at": war.ends_at,
                "ended_at": war.ended_at,
                "tracked_matches": counts.get(war.id, {}).get("counted", 0),
                "rejected_matches": (
                    counts.get(war.id, {}).get("total", 0)
                    - counts.get(war.id, {}).get("counted", 0)
                ),
            }
            for war in wars
        ]
    }


@router.get("/wars/{war_id}")
def get_admin_war(
    war_id: int,
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    service = ClanWarService()
    return service.serialize_war(db, service.get_war(db, war_id))


@router.post("/wars/{war_id}/recalculate")
def recalculate_admin_war(
    war_id: int,
    request: AdminReasonRequest,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    service = ClanWarService()
    war = db.query(ClanWar).filter(ClanWar.id == war_id).with_for_update().first()
    if not war:
        raise HTTPException(status_code=404, detail="Война не найдена")
    before = service.serialize_war(db, war)
    result = service.recalculate_active_war(db, war.id, commit=False, allow_finished=True)
    after = service.serialize_war(db, war)
    AdminAuditService().record(
        db,
        actor_user_id=current_admin.id,
        action="war_recalculated",
        entity_type="clan_war",
        entity_id=war.id,
        before_data={
            "tracked_matches": before["tracked_matches"],
            "rejected_matches": before["rejected_matches"],
            "scores": before["clan_scores"],
        },
        after_data={
            "tracked_matches": after["tracked_matches"],
            "rejected_matches": after["rejected_matches"],
            "scores": result["scores"],
        },
        reason=request.reason,
    )
    db.commit()
    return service.serialize_war(db, war)


@router.patch("/wars/{war_id}/matches/{result_id}")
def review_admin_war_match(
    war_id: int,
    result_id: int,
    request: WarMatchReviewRequest,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    war = db.query(ClanWar).filter(ClanWar.id == war_id).with_for_update().first()
    if not war:
        raise HTTPException(status_code=404, detail="Война не найдена")
    result = (
        db.query(ClanWarMatchResult)
        .filter(
            ClanWarMatchResult.id == result_id,
            ClanWarMatchResult.war_id == war.id,
        )
        .with_for_update()
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="Матч этой войны не найден")

    before = {
        "is_counted": result.is_counted,
        "rejection_reason": result.rejection_reason,
        "admin_override": result.admin_override,
        "admin_override_reason": result.admin_override_reason,
    }
    result.admin_override = {
        "count": True,
        "exclude": False,
        "automatic": None,
    }[request.mode]
    result.admin_override_reason = None if request.mode == "automatic" else request.reason
    result.admin_override_by_user_id = None if request.mode == "automatic" else current_admin.id
    result.admin_override_at = None if request.mode == "automatic" else utc_now()
    db.flush()

    service = ClanWarService()
    service.recalculate_active_war(db, war.id, commit=False, allow_finished=True)
    after = {
        "is_counted": result.is_counted,
        "rejection_reason": result.rejection_reason,
        "admin_override": result.admin_override,
        "admin_override_reason": result.admin_override_reason,
    }
    AdminAuditService().record(
        db,
        actor_user_id=current_admin.id,
        action="war_match_reviewed",
        entity_type="clan_war_match_result",
        entity_id=result.id,
        before_data=before,
        after_data=after,
        reason=request.reason,
    )
    db.commit()
    return service.serialize_war(db, war)


@router.post("/wars/{war_id}/extend")
def extend_admin_war(
    war_id: int,
    request: WarExtensionRequest,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    service = ClanWarService()
    war = db.query(ClanWar).filter(ClanWar.id == war_id).with_for_update().first()
    if not war:
        raise HTTPException(status_code=404, detail="Война не найдена")
    before = _war_audit_state(war)
    service.extend_war(db, war.id, request.hours, commit=False)
    AdminAuditService().record(
        db,
        actor_user_id=current_admin.id,
        action="war_extended",
        entity_type="clan_war",
        entity_id=war.id,
        before_data=before,
        after_data=_war_audit_state(war),
        reason=request.reason,
    )
    db.commit()
    return service.serialize_war(db, war)


@router.post("/wars/{war_id}/finish")
def finish_admin_war(
    war_id: int,
    request: WarFinishRequest,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    service = ClanWarService()
    war = db.query(ClanWar).filter(ClanWar.id == war_id).first()
    if not war:
        raise HTTPException(status_code=404, detail="Война не найдена")
    ResourceLedgerService.lock_clans(db, [war.attacking_clan_id, war.defending_clan_id])
    db.refresh(war, with_for_update=True)
    if war.status != "active":
        raise HTTPException(status_code=409, detail="Война уже завершена")
    if request.winner_clan_id not in {war.attacking_clan_id, war.defending_clan_id}:
        raise HTTPException(status_code=400, detail="Победитель должен быть стороной этой войны")
    before = _war_audit_state(war)
    service._complete_war(db, war, request.winner_clan_id, commit=False)
    AdminAuditService().record(
        db,
        actor_user_id=current_admin.id,
        action="war_finished_manually",
        entity_type="clan_war",
        entity_id=war.id,
        before_data=before,
        after_data=_war_audit_state(war),
        reason=request.reason,
    )
    db.commit()
    return service.serialize_war(db, war)


@router.post("/wars/{war_id}/cancel")
def cancel_admin_war(
    war_id: int,
    request: AdminReasonRequest,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    service = ClanWarService()
    war = db.query(ClanWar).filter(ClanWar.id == war_id).with_for_update().first()
    if not war:
        raise HTTPException(status_code=404, detail="Война не найдена")
    before = _war_audit_state(war)
    service.cancel_war(db, war.id, refund_attack=True, commit=False)
    AdminAuditService().record(
        db,
        actor_user_id=current_admin.id,
        action="war_canceled",
        entity_type="clan_war",
        entity_id=war.id,
        before_data=before,
        after_data=_war_audit_state(war),
        reason=request.reason,
    )
    db.commit()
    return service.serialize_war(db, war)


@router.get("/ledger")
def get_resource_ledger(
    clan_id: int | None = Query(None, ge=1),
    resource: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(ResourceLedgerEntry, Clan.name, User.username)
        .join(Clan, Clan.id == ResourceLedgerEntry.clan_id)
        .outerjoin(User, User.id == ResourceLedgerEntry.actor_user_id)
    )
    if clan_id:
        query = query.filter(ResourceLedgerEntry.clan_id == clan_id)
    if resource:
        query = query.filter(ResourceLedgerEntry.resource == resource.strip().lower())
    rows = query.order_by(ResourceLedgerEntry.created_at.desc(), ResourceLedgerEntry.id.desc()).limit(limit).all()
    return {
        "entries": [
            {
                "id": entry.id,
                "clan_id": entry.clan_id,
                "clan_name": clan_name,
                "resource": entry.resource,
                "amount": entry.amount,
                "balance_before": entry.balance_before,
                "balance_after": entry.balance_after,
                "action": entry.action,
                "actor": actor,
                "details": entry.details,
                "created_at": entry.created_at,
            }
            for entry, clan_name, actor in rows
        ]
    }


@router.get("/audit")
def get_admin_audit(
    action: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(AdminAuditLog, User.username)
        .join(User, User.id == AdminAuditLog.actor_user_id)
    )
    if action:
        query = query.filter(AdminAuditLog.action == action.strip())
    rows = query.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc()).limit(limit).all()
    return {
        "entries": [
            {
                "id": entry.id,
                "actor": actor,
                "action": entry.action,
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
                "before": entry.before_data,
                "after": entry.after_data,
                "reason": entry.reason,
                "created_at": entry.created_at,
            }
            for entry, actor in rows
        ]
    }
