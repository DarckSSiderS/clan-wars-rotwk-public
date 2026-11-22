from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.time import utc_now
from app.models.feedback import FeedbackMessage, FeedbackTicket
from app.models.role import Role
from app.models.user import User
from app.schemas.feedback import FeedbackAdminUpdate, FeedbackTicketCreate
from app.services.notification_service import notification_service
from app.services.operation_service import AdminAuditService
from app.services.realtime_service import queue_realtime_event


ACTIVE_STATUSES = ("new", "in_progress", "waiting_user")


class FeedbackService:
    @staticmethod
    def _ticket_query(db: Session):
        return db.query(FeedbackTicket).options(
            joinedload(FeedbackTicket.reporter),
            joinedload(FeedbackTicket.assigned_admin),
            selectinload(FeedbackTicket.messages).joinedload(FeedbackMessage.author),
        )

    @staticmethod
    def _admin_ids(db: Session) -> set[int]:
        return {
            int(user_id)
            for (user_id,) in (
                db.query(User.id)
                .join(Role, Role.id == User.role_id)
                .filter(Role.name == "admin", User.is_active.is_(True))
                .all()
            )
        }

    @staticmethod
    def _message_payload(message: FeedbackMessage) -> dict:
        return {
            "id": int(message.id),
            "author_id": int(message.author_id) if message.author_id is not None else None,
            "author_name": (
                message.author.display_name or message.author.username
                if message.author
                else "Удалённый пользователь"
            ),
            "body": message.body,
            "is_admin": bool(message.is_admin),
            "created_at": message.created_at,
        }

    def payload(self, ticket: FeedbackTicket) -> dict:
        return {
            "id": int(ticket.id),
            "reference": f"CW-{int(ticket.id):06d}",
            "reporter_id": int(ticket.reporter_id),
            "reporter_name": (
                ticket.reporter.display_name or ticket.reporter.username
                if ticket.reporter
                else "Удалённый пользователь"
            ),
            "assigned_admin_id": (
                int(ticket.assigned_admin_id)
                if ticket.assigned_admin_id is not None
                else None
            ),
            "assigned_admin_name": (
                ticket.assigned_admin.display_name or ticket.assigned_admin.username
                if ticket.assigned_admin
                else None
            ),
            "category": ticket.category,
            "title": ticket.title,
            "description": ticket.description,
            "reproduction_steps": ticket.reproduction_steps,
            "expected_result": ticket.expected_result,
            "actual_result": ticket.actual_result,
            "attachment_url": ticket.attachment_url,
            "source_path": ticket.source_path,
            "user_agent": ticket.user_agent,
            "status": ticket.status,
            "priority": ticket.priority,
            "admin_unread": bool(ticket.admin_unread),
            "created_at": ticket.created_at,
            "updated_at": ticket.updated_at,
            "resolved_at": ticket.resolved_at,
            "messages": [self._message_payload(message) for message in ticket.messages],
        }

    def create(
        self,
        db: Session,
        *,
        reporter: User,
        data: FeedbackTicketCreate,
        attachment_url: str | None = None,
    ) -> dict:
        ticket = FeedbackTicket(
            reporter_id=reporter.id,
            category=data.category,
            title=data.title,
            description=data.description,
            reproduction_steps=data.reproduction_steps,
            expected_result=data.expected_result,
            actual_result=data.actual_result,
            attachment_url=attachment_url,
            source_path=data.source_path,
            user_agent=data.user_agent,
            status="new",
            priority="normal",
            admin_unread=True,
        )
        db.add(ticket)
        db.flush([ticket])

        admin_ids = self._admin_ids(db)
        for admin_id in admin_ids:
            notification_service.create(
                db,
                user_id=admin_id,
                notification_type="feedback_created",
                title="Новое обращение пользователя",
                message=f"{reporter.username}: {ticket.title}",
                link_url=f"/admin?section=feedback&ticket={ticket.id}",
                entity_type="feedback_ticket",
                entity_id=ticket.id,
                commit=False,
            )
        queue_realtime_event(
            db,
            user_ids=admin_ids,
            payload={"type": "feedback.created", "ticket_id": ticket.id},
        )
        db.commit()
        return self.get_for_user(db, ticket_id=ticket.id, user=reporter)

    def list_for_user(self, db: Session, *, user: User) -> list[dict]:
        tickets = (
            self._ticket_query(db)
            .filter(FeedbackTicket.reporter_id == user.id)
            .order_by(FeedbackTicket.updated_at.desc(), FeedbackTicket.id.desc())
            .all()
        )
        return [self.payload(ticket) for ticket in tickets]

    def get_for_user(self, db: Session, *, ticket_id: int, user: User) -> dict:
        ticket = (
            self._ticket_query(db)
            .filter(
                FeedbackTicket.id == ticket_id,
                FeedbackTicket.reporter_id == user.id,
            )
            .first()
        )
        if ticket is None:
            raise LookupError("Обращение не найдено")
        return self.payload(ticket)

    def add_user_reply(
        self,
        db: Session,
        *,
        ticket_id: int,
        user: User,
        body: str,
    ) -> dict:
        ticket = (
            db.query(FeedbackTicket)
            .filter(
                FeedbackTicket.id == ticket_id,
                FeedbackTicket.reporter_id == user.id,
            )
            .first()
        )
        if ticket is None:
            raise LookupError("Обращение не найдено")
        message = FeedbackMessage(
            ticket_id=ticket.id,
            author_id=user.id,
            body=body.strip(),
            is_admin=False,
        )
        db.add(message)
        ticket.admin_unread = True
        ticket.updated_at = utc_now()
        if ticket.status in {"waiting_user", "resolved", "closed"}:
            ticket.status = "in_progress"
            ticket.resolved_at = None

        admin_ids = self._admin_ids(db)
        for admin_id in admin_ids:
            notification_service.create(
                db,
                user_id=admin_id,
                notification_type="feedback_reply",
                title=f"Ответ по обращению CW-{ticket.id:06d}",
                message=f"{user.username}: {body.strip()[:180]}",
                link_url=f"/admin?section=feedback&ticket={ticket.id}",
                entity_type="feedback_ticket",
                entity_id=ticket.id,
                commit=False,
            )
        queue_realtime_event(
            db,
            user_ids=admin_ids,
            payload={"type": "feedback.user_replied", "ticket_id": ticket.id},
        )
        db.commit()
        return self.get_for_user(db, ticket_id=ticket.id, user=user)

    def list_admin(
        self,
        db: Session,
        *,
        status: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        search: str | None = None,
        limit: int = 200,
    ) -> dict:
        query = self._ticket_query(db)
        if status and status != "all":
            query = query.filter(FeedbackTicket.status == status)
        if category and category != "all":
            query = query.filter(FeedbackTicket.category == category)
        if priority and priority != "all":
            query = query.filter(FeedbackTicket.priority == priority)
        if search:
            term = f"%{search.strip()}%"
            query = query.join(User, User.id == FeedbackTicket.reporter_id).filter(or_(
                FeedbackTicket.title.ilike(term),
                FeedbackTicket.description.ilike(term),
                User.username.ilike(term),
                User.display_name.ilike(term),
            ))
        total = query.count()
        tickets = (
            query.order_by(
                FeedbackTicket.admin_unread.desc(),
                FeedbackTicket.updated_at.desc(),
                FeedbackTicket.id.desc(),
            )
            .limit(limit)
            .all()
        )
        base = db.query(FeedbackTicket)
        summary = {
            "total": int(base.count()),
            "unread": int(base.filter(FeedbackTicket.admin_unread.is_(True)).count()),
            "new": int(base.filter(FeedbackTicket.status == "new").count()),
            "in_progress": int(base.filter(FeedbackTicket.status.in_(ACTIVE_STATUSES[1:])).count()),
            "critical": int(base.filter(
                FeedbackTicket.priority == "critical",
                FeedbackTicket.status.in_(ACTIVE_STATUSES),
            ).count()),
        }
        return {
            "items": [self.payload(ticket) for ticket in tickets],
            "total": int(total),
            "summary": summary,
        }

    def get_admin(self, db: Session, *, ticket_id: int) -> FeedbackTicket:
        ticket = self._ticket_query(db).filter(FeedbackTicket.id == ticket_id).first()
        if ticket is None:
            raise LookupError("Обращение не найдено")
        return ticket

    def mark_admin_read(self, db: Session, *, ticket_id: int) -> dict:
        ticket = self.get_admin(db, ticket_id=ticket_id)
        if ticket.admin_unread:
            ticket.admin_unread = False
            db.commit()
        return self.payload(self.get_admin(db, ticket_id=ticket_id))

    def admin_update(
        self,
        db: Session,
        *,
        ticket_id: int,
        admin: User,
        data: FeedbackAdminUpdate,
    ) -> dict:
        ticket = self.get_admin(db, ticket_id=ticket_id)
        before = {
            "status": ticket.status,
            "priority": ticket.priority,
            "assigned_admin_id": ticket.assigned_admin_id,
        }
        if data.status is not None:
            ticket.status = data.status
            ticket.resolved_at = utc_now() if data.status in {"resolved", "closed"} else None
        if data.priority is not None:
            ticket.priority = data.priority
        if data.assign_to_me is True:
            ticket.assigned_admin_id = admin.id
        elif data.assign_to_me is False:
            ticket.assigned_admin_id = None
        ticket.admin_unread = False
        ticket.updated_at = utc_now()
        after = {
            "status": ticket.status,
            "priority": ticket.priority,
            "assigned_admin_id": ticket.assigned_admin_id,
        }
        AdminAuditService().record(
            db,
            actor_user_id=admin.id,
            action="feedback_ticket_updated",
            entity_type="feedback_ticket",
            entity_id=ticket.id,
            before_data=before,
            after_data=after,
            reason="Обработка обращения пользователя",
        )
        if before["status"] != after["status"]:
            notification_service.create(
                db,
                user_id=ticket.reporter_id,
                notification_type="feedback_status",
                title=f"Статус обращения CW-{ticket.id:06d} изменён",
                message=f"Новый статус: {ticket.status}",
                link_url=f"/feedback?ticket={ticket.id}",
                entity_type="feedback_ticket",
                entity_id=ticket.id,
                commit=False,
            )
        queue_realtime_event(
            db,
            user_ids={ticket.reporter_id},
            payload={"type": "feedback.updated", "ticket_id": ticket.id},
        )
        db.commit()
        return self.payload(self.get_admin(db, ticket_id=ticket.id))

    def admin_reply(
        self,
        db: Session,
        *,
        ticket_id: int,
        admin: User,
        body: str,
    ) -> dict:
        ticket = self.get_admin(db, ticket_id=ticket_id)
        db.add(FeedbackMessage(
            ticket_id=ticket.id,
            author_id=admin.id,
            body=body.strip(),
            is_admin=True,
        ))
        if ticket.assigned_admin_id is None:
            ticket.assigned_admin_id = admin.id
        if ticket.status not in {"resolved", "closed"}:
            ticket.status = "waiting_user"
        ticket.admin_unread = False
        ticket.updated_at = utc_now()
        notification_service.create(
            db,
            user_id=ticket.reporter_id,
            notification_type="feedback_reply",
            title=f"Ответ по обращению CW-{ticket.id:06d}",
            message=body.strip()[:240],
            link_url=f"/feedback?ticket={ticket.id}",
            entity_type="feedback_ticket",
            entity_id=ticket.id,
            commit=False,
        )
        AdminAuditService().record(
            db,
            actor_user_id=admin.id,
            action="feedback_admin_replied",
            entity_type="feedback_ticket",
            entity_id=ticket.id,
            after_data={"status": ticket.status},
            reason="Ответ пользователю",
        )
        queue_realtime_event(
            db,
            user_ids={ticket.reporter_id},
            payload={"type": "feedback.admin_replied", "ticket_id": ticket.id},
        )
        db.commit()
        return self.payload(self.get_admin(db, ticket_id=ticket.id))


feedback_service = FeedbackService()
