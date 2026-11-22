from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user
from app.database import get_db
from app.models.campaign import CampaignRuleSet
from app.models.user import User
from app.schemas.campaign_rules import CampaignRuleRestore, CampaignRuleUpdate
from app.services.campaign_rule_service import (
    CampaignRuleInputError,
    CampaignRuleService,
    CampaignRuleVersionConflict,
)


router = APIRouter(
    prefix="/admin/campaign-rules",
    tags=["admin-campaign-rules"],
)


def _serialize_rule_set(row: CampaignRuleSet) -> dict[str, object]:
    return {
        "id": row.id,
        "version": row.version,
        "values": dict(row.values),
        "is_active": row.is_active,
        "created_by_user_id": row.created_by_user_id,
        "reason": row.reason,
        "created_at": row.created_at,
    }


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, CampaignRuleVersionConflict):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "campaign_rule_version_conflict",
                "expected_version": exc.expected_version,
                "active_version": exc.active_version,
            },
        ) from exc
    if isinstance(exc, CampaignRuleInputError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "campaign_rule_validation_failed",
                "errors": [asdict(error) for error in exc.errors],
            },
        ) from exc
    raise exc


@router.get("")
def get_campaign_rules(
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    service = CampaignRuleService()
    active = service.get_active(db)
    return {
        "active": {
            "id": active.id,
            "version": active.version,
            "values": dict(active.values),
            "is_active": True,
        },
        "schema": service.schema(),
    }


@router.get("/history")
def get_campaign_rule_history(
    limit: int = Query(default=100, ge=1, le=500),
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    return {
        "items": [
            _serialize_rule_set(row)
            for row in CampaignRuleService().history(db, limit=limit)
        ]
    }


@router.put("")
def update_campaign_rules(
    payload: CampaignRuleUpdate,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    try:
        row = CampaignRuleService().create_version(
            db,
            expected_version=payload.expected_version,
            changes=payload.changes,
            actor_user_id=current_admin.id,
            reason=payload.reason,
            commit=True,
        )
    except (CampaignRuleVersionConflict, CampaignRuleInputError) as exc:
        _raise_service_error(exc)
    return _serialize_rule_set(row)


@router.post("/{version:int}/restore")
def restore_campaign_rules(
    version: int,
    payload: CampaignRuleRestore,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    try:
        row = CampaignRuleService().restore_version(
            db,
            source_version=version,
            expected_version=payload.expected_version,
            actor_user_id=current_admin.id,
            reason=payload.reason,
            commit=True,
        )
    except (CampaignRuleVersionConflict, CampaignRuleInputError) as exc:
        _raise_service_error(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "campaign_rule_version_not_found",
                "version": version,
            },
        ) from exc
    return _serialize_rule_set(row)
