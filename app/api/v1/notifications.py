from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.database import get_db
from app.models.user import User
from app.schemas.notification import (
    Notification,
    NotificationList,
    NotificationReadAllResult,
    NotificationUnreadCount,
)
from app.services.notification_service import notification_service


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationList)
def get_notifications(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    unread_only: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    items, total, unread_count = notification_service.list_for_user(
        db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        unread_only=unread_only,
    )
    return {
        "items": items,
        "total": total,
        "unread_count": unread_count,
    }


@router.get("/unread-count", response_model=NotificationUnreadCount)
def get_unread_notification_count(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return {
        "unread_count": notification_service.unread_count(
            db,
            user_id=current_user.id,
        )
    }


@router.put("/read-all", response_model=NotificationReadAllResult)
def mark_all_notifications_read(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return {
        "updated": notification_service.mark_all_read(
            db,
            user_id=current_user.id,
        )
    }


@router.put("/{notification_id:int}/read", response_model=Notification)
def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    notification = notification_service.mark_read(
        db,
        user_id=current_user.id,
        notification_id=notification_id,
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Уведомление не найдено")
    return notification
