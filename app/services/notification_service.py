from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.notification import UserNotification
from app.services.realtime_service import queue_realtime_event


class NotificationService:
    """Персональная лента событий без демонстрационных записей."""

    def create(
        self,
        db: Session,
        *,
        user_id: int,
        notification_type: str,
        title: str,
        message: str,
        link_url: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        commit: bool = True,
    ) -> UserNotification:
        notification = UserNotification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            link_url=link_url,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        db.add(notification)
        db.flush([notification])
        queue_realtime_event(
            db,
            user_ids={user_id},
            payload={
                "type": "notification.created",
                "notification": {
                    "id": notification.id,
                    "notification_type": notification.notification_type,
                    "title": notification.title,
                    "message": notification.message,
                    "link_url": notification.link_url,
                    "entity_type": notification.entity_type,
                    "entity_id": notification.entity_id,
                    "created_at": notification.created_at.isoformat()
                    if notification.created_at
                    else None,
                    "read_at": None,
                },
            },
        )
        if commit:
            db.commit()
            db.refresh(notification)
        return notification

    def create_for_clan(
        self,
        db: Session,
        *,
        clan_id: int | None,
        notification_type: str,
        title: str,
        message: str,
        link_url: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        excluded_user_id: Optional[int] = None,
        commit: bool = False,
    ) -> int:
        if clan_id is None:
            return 0
        from app.models.clan import ClanMember

        user_ids = {
            user_id
            for (user_id,) in (
                db.query(ClanMember.user_id)
                .filter(ClanMember.clan_id == clan_id)
                .all()
            )
            if user_id != excluded_user_id
        }
        for user_id in user_ids:
            self.create(
                db,
                user_id=user_id,
                notification_type=notification_type,
                title=title,
                message=message,
                link_url=link_url,
                entity_type=entity_type,
                entity_id=entity_id,
                commit=False,
            )
        if commit and user_ids:
            db.commit()
        return len(user_ids)

    def list_for_user(
        self,
        db: Session,
        *,
        user_id: int,
        skip: int = 0,
        limit: int = 30,
        unread_only: bool = False,
    ) -> tuple[list[UserNotification], int, int]:
        query = db.query(UserNotification).filter(UserNotification.user_id == user_id)
        if unread_only:
            query = query.filter(UserNotification.read_at.is_(None))
        total = query.count()
        items = (
            query.order_by(
                UserNotification.created_at.desc(),
                UserNotification.id.desc(),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )
        return items, total, self.unread_count(db, user_id=user_id)

    def unread_count(self, db: Session, *, user_id: int) -> int:
        return int(
            db.query(func.count(UserNotification.id))
            .filter(
                UserNotification.user_id == user_id,
                UserNotification.read_at.is_(None),
            )
            .scalar()
            or 0
        )

    def mark_read(
        self,
        db: Session,
        *,
        user_id: int,
        notification_id: int,
    ) -> Optional[UserNotification]:
        notification = (
            db.query(UserNotification)
            .filter(
                UserNotification.id == notification_id,
                UserNotification.user_id == user_id,
            )
            .first()
        )
        if notification is None:
            return None
        if notification.read_at is None:
            notification.read_at = utc_now()
            queue_realtime_event(
                db,
                user_ids={user_id},
                payload={
                    "type": "notification.read",
                    "notification_id": notification.id,
                },
            )
            db.commit()
            db.refresh(notification)
        return notification

    def mark_all_read(self, db: Session, *, user_id: int) -> int:
        notifications = (
            db.query(UserNotification)
            .filter(
                UserNotification.user_id == user_id,
                UserNotification.read_at.is_(None),
            )
            .all()
        )
        if not notifications:
            return 0
        read_at = utc_now()
        for notification in notifications:
            notification.read_at = read_at
        queue_realtime_event(
            db,
            user_ids={user_id},
            payload={
                "type": "notifications.read_all",
                "notification_ids": [item.id for item in notifications],
            },
        )
        db.commit()
        return len(notifications)


notification_service = NotificationService()
