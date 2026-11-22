import json
from pathlib import Path

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.core.auth import get_current_active_user, get_current_admin_user
from app.models.user import User as UserModel
from app.models.match import Match
from app.models.campaign import ReplaySyncState
from app.database import get_db
from app.services.scheduler_service import WorkerStatusService
from app.services.campaign_settings_service import (
    CampaignSettingsService,
    ReplaySyncStateService,
)
from app.services.operation_service import AdminAuditService
from app.services.replay_storage_service import ReplayStorageService
from app.services.map_preview_storage_service import MapPreviewStorageService
from app.config import settings
from app.services.campaign_pause_service import CampaignPauseService
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["scheduler"])
map_preview_storage = MapPreviewStorageService()


class CampaignPatchSettingsUpdate(BaseModel):
    patch_202_enabled: bool
    ennorath_enabled: bool


class CampaignPauseRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def _serialize_campaign_settings(campaign) -> dict:
    return {
        "patch_202_enabled": bool(campaign.patch_202_enabled),
        "ennorath_enabled": bool(campaign.ennorath_enabled),
        "updated_by": campaign.updated_by,
        "updated_at": campaign.updated_at,
        "is_paused": bool(campaign.is_paused),
        "paused_at": campaign.paused_at,
        "pause_reason": campaign.pause_reason,
    }


def _serialize_replay_state(state) -> dict:
    return {
        "replay_id": state.replay_id,
        "status": state.status,
        "patch_family": state.patch_family,
        "patch_name": state.patch_name,
        "reason": state.reason,
        "attempts": state.attempts,
        "first_seen_at": state.first_seen_at,
        "last_attempt_at": state.last_attempt_at,
        "imported_at": state.imported_at,
    }


def _parse_json_text(value):
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _serialize_match(match: Match) -> dict:
    payload = {
        column.name: getattr(match, column.name)
        for column in Match.__table__.columns
    }
    payload["likes"] = _parse_json_text(match.likes)
    payload["comments"] = _parse_json_text(match.comments)
    payload["replay_file_exists"] = bool(
        match.replay_local_path and Path(match.replay_local_path).is_file()
    )
    payload["map_preview_url"] = map_preview_storage.public_url(match.map_name)
    payload["participants"] = [
        {
            "nickname": participant.nickname,
            "player_uuid": participant.player_uuid,
            "faction": participant.faction,
            "team": participant.team,
            "is_winner": bool(participant.is_winner),
            "is_observer": bool(participant.is_observer),
            "old_rank": participant.old_rank,
            "new_rank": participant.new_rank,
            "elo": participant.elo,
        }
        for participant in sorted(
            match.participants or [],
            key=lambda item: (
                not bool(item.is_winner),
                item.team if item.team is not None else 99,
                item.nickname.casefold(),
            ),
        )
    ]
    return payload



@router.get("/status")
async def get_scheduler_status(
    current_user: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Получает статус планировщика"""
    try:
        return WorkerStatusService().get_status(db)
    except Exception as e:
        logger.error(f"Ошибка получения статуса планировщика: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения статуса")


@router.get("/admin-overview")
def get_admin_sync_overview(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    if status and status not in {"imported", "known", "skipped", "error"}:
        raise HTTPException(status_code=422, detail="Неизвестный статус replay")
    campaign_service = CampaignSettingsService()
    replay_service = ReplaySyncStateService()
    campaign = campaign_service.get_or_create(db)
    return {
        "worker": WorkerStatusService().get_status(db),
        "campaign": _serialize_campaign_settings(campaign),
        "summary": replay_service.summary(db),
        "replays": [
            _serialize_replay_state(state)
            for state in replay_service.list_states(db, status=status, limit=limit)
        ],
    }


@router.get("/campaign-settings")
def get_campaign_patch_settings(
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    campaign = CampaignSettingsService().get_or_create(db)
    return {
        "patch_202_enabled": bool(campaign.patch_202_enabled),
        "ennorath_enabled": bool(campaign.ennorath_enabled),
        "updated_at": campaign.updated_at,
    }


@router.get("/replays/{replay_id}")
def get_replay_detail(
    replay_id: str,
    current_user: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    state = db.get(ReplaySyncState, replay_id)
    match = db.query(Match).filter(Match.match_id == replay_id).first()
    if state is None and match is None:
        raise HTTPException(status_code=404, detail="Replay не найден")
    return {
        "sync": _serialize_replay_state(state) if state else None,
        "match": _serialize_match(match) if match else None,
    }


@router.post("/replays/{replay_id}/download")
async def download_replay_to_archive(
    replay_id: str,
    current_user: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    match = db.query(Match).filter(Match.match_id == replay_id).first()
    if match is None:
        raise HTTPException(status_code=404, detail="Матч не найден в базе")
    storage = ReplayStorageService()
    if not storage.is_supported(match):
        raise HTTPException(
            status_code=422,
            detail="Архивируются только Ennorath и Patch 2.02",
        )
    timeout = aiohttp.ClientTimeout(total=120, connect=20)
    connector = aiohttp.TCPConnector()
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
    ) as session:
        success = await storage.download_match(db, match, session)
    if not success:
        raise HTTPException(
            status_code=502,
            detail=match.replay_download_error or "Не удалось скачать replay",
        )
    return _serialize_match(match)


@router.get("/replays/{replay_id}/file")
def get_archived_replay_file(
    replay_id: str,
    current_user: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    match = db.query(Match).filter(Match.match_id == replay_id).first()
    if match is None or not match.replay_local_path:
        raise HTTPException(status_code=404, detail="Файл replay еще не сохранен")
    storage_root = Path(settings.REPLAY_STORAGE_DIR).resolve()
    replay_path = Path(match.replay_local_path).resolve()
    try:
        replay_path.relative_to(storage_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Недопустимый путь replay") from exc
    if not replay_path.is_file():
        raise HTTPException(status_code=404, detail="Файл replay отсутствует на диске")
    return FileResponse(
        replay_path,
        media_type="application/octet-stream",
        filename=replay_path.name,
    )


@router.put("/campaign-settings")
def update_campaign_patch_settings(
    payload: CampaignPatchSettingsUpdate,
    current_user: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    campaign_service = CampaignSettingsService()
    current = campaign_service.get_or_create(db)
    before = _serialize_campaign_settings(current)
    try:
        campaign = campaign_service.update(
            db,
            patch_202_enabled=payload.patch_202_enabled,
            ennorath_enabled=payload.ennorath_enabled,
            updated_by=current_user.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    after = _serialize_campaign_settings(campaign)
    AdminAuditService().record(
        db,
        actor_user_id=current_user.id,
        action="campaign_patches_updated",
        entity_type="campaign_settings",
        entity_id=campaign.id,
        before_data={
            "patch_202_enabled": before["patch_202_enabled"],
            "ennorath_enabled": before["ennorath_enabled"],
        },
        after_data={
            "patch_202_enabled": after["patch_202_enabled"],
            "ennorath_enabled": after["ennorath_enabled"],
        },
        reason="Изменение активных патчей текущего сезона",
    )
    db.commit()
    return after


@router.post("/campaign/pause")
def pause_campaign(
    payload: CampaignPauseRequest,
    current_user: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    try:
        campaign = CampaignPauseService().pause(
            db,
            actor_user_id=current_user.id,
            reason=payload.reason,
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error
    return _serialize_campaign_settings(campaign)


@router.post("/campaign/resume")
def resume_campaign(
    payload: CampaignPauseRequest,
    current_user: UserModel = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    campaign = CampaignPauseService().resume(
        db,
        actor_user_id=current_user.id,
        reason=payload.reason,
    )
    return _serialize_campaign_settings(campaign)


@router.post("/fetch-matches")
async def fetch_matches_manual(
    current_user: UserModel = Depends(get_current_admin_user),
    limit: int = Query(default=15, ge=1, le=100),
):
    """Ручное получение матчей (только для администраторов)"""
    try:
        from app.services.ladder_service import ladder_service
        from app.database import SessionLocal
        
        db = SessionLocal()
        try:
            saved_count = await ladder_service.fetch_and_save_matches(db, limit=limit)
            return {
                "message": f"Получено и сохранено {saved_count} новых матчей",
                "saved_count": saved_count,
                "source": ladder_service.last_source,
                "scanned_count": ladder_service.last_scanned_count,
            }
        finally:
            db.close()
    except Exception:
        logger.exception("Ошибка ручной синхронизации матчей")
        raise HTTPException(
            status_code=502,
            detail="Источник матчей временно недоступен или вернул некорректный ответ",
        )
