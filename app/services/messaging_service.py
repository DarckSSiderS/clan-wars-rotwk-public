from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.time import utc_now
from app.models.messaging import DirectConversation, DirectMessage, DirectMessageReport, UserBlock
from app.models.user import User
from app.services.notification_service import notification_service
from app.services.realtime_service import queue_realtime_event
from app.services.user_service import UserService


class MessagingService:
    @staticmethod
    def _pair(first_user_id: int, second_user_id: int) -> tuple[int, int]:
        if first_user_id == second_user_id:
            raise HTTPException(status_code=400, detail="Нельзя создать диалог с самим собой")
        return tuple(sorted((int(first_user_id), int(second_user_id))))

    @staticmethod
    def _user_by_username(db: Session, username: str) -> User:
        user = UserService().get_public_profile(db, username)
        if user is None or not user.is_active or not user.is_claimed:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        return user

    @staticmethod
    def _public_name(user: User) -> str:
        return str(user.display_name or user.username).strip()

    @staticmethod
    def _conversation_query(db: Session):
        return db.query(DirectConversation).options(
            joinedload(DirectConversation.user_low),
            joinedload(DirectConversation.user_high),
        )

    def _require_conversation(self, db: Session, conversation_id: int, user: User) -> DirectConversation:
        conversation = self._conversation_query(db).filter(
            DirectConversation.id == conversation_id,
            or_(
                DirectConversation.user_low_id == user.id,
                DirectConversation.user_high_id == user.id,
            ),
        ).first()
        if conversation is None:
            raise HTTPException(status_code=404, detail="Диалог не найден")
        return conversation

    @staticmethod
    def _counterpart(conversation: DirectConversation, user_id: int) -> User:
        return conversation.user_high if conversation.user_low_id == user_id else conversation.user_low

    @staticmethod
    def _serialize_message(message: DirectMessage) -> dict:
        return {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "sender_id": message.sender_id,
            "sender_username": message.sender.username if message.sender else "",
            "body": message.body,
            "created_at": message.created_at,
            "read_at": message.read_at,
        }

    def _serialize_conversation(self, db: Session, conversation: DirectConversation, user_id: int) -> dict:
        counterpart = self._counterpart(conversation, user_id)
        last_message = (
            db.query(DirectMessage)
            .options(joinedload(DirectMessage.sender))
            .filter(DirectMessage.conversation_id == conversation.id)
            .order_by(DirectMessage.created_at.desc(), DirectMessage.id.desc())
            .first()
        )
        unread_count = db.query(func.count(DirectMessage.id)).filter(
            DirectMessage.conversation_id == conversation.id,
            DirectMessage.sender_id != user_id,
            DirectMessage.read_at.is_(None),
        ).scalar() or 0
        return {
            "id": conversation.id,
            "counterpart": {
                "id": counterpart.id,
                "username": counterpart.username,
                "display_name": self._public_name(counterpart),
                "avatar_url": counterpart.avatar_url,
            },
            "last_message": self._serialize_message(last_message) if last_message else None,
            "unread_count": int(unread_count),
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        }

    def _is_blocked(self, db: Session, first_user_id: int, second_user_id: int) -> bool:
        return db.query(UserBlock.id).filter(
            or_(
                (UserBlock.blocker_id == first_user_id) & (UserBlock.blocked_id == second_user_id),
                (UserBlock.blocker_id == second_user_id) & (UserBlock.blocked_id == first_user_id),
            )
        ).first() is not None

    def get_or_create(self, db: Session, *, user: User, username: str) -> dict:
        counterpart = self._user_by_username(db, username)
        low_id, high_id = self._pair(user.id, counterpart.id)
        conversation = self._conversation_query(db).filter(
            DirectConversation.user_low_id == low_id,
            DirectConversation.user_high_id == high_id,
        ).first()
        if conversation is None:
            if self._is_blocked(db, user.id, counterpart.id):
                raise HTTPException(status_code=403, detail="Диалог недоступен")
            conversation = DirectConversation(user_low_id=low_id, user_high_id=high_id)
            db.add(conversation)
            db.commit()
            conversation = self._conversation_query(db).filter(DirectConversation.id == conversation.id).first()
        return self._serialize_conversation(db, conversation, user.id)

    def list_conversations(self, db: Session, *, user: User, limit: int = 50) -> list[dict]:
        conversations = self._conversation_query(db).filter(
            or_(
                DirectConversation.user_low_id == user.id,
                DirectConversation.user_high_id == user.id,
            )
        ).order_by(DirectConversation.updated_at.desc()).limit(limit).all()
        return [self._serialize_conversation(db, conversation, user.id) for conversation in conversations]

    def list_messages(
        self,
        db: Session,
        *,
        user: User,
        conversation_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> dict:
        conversation = self._require_conversation(db, conversation_id, user)
        query = db.query(DirectMessage).options(joinedload(DirectMessage.sender)).filter(
            DirectMessage.conversation_id == conversation.id
        )
        total = query.count()
        # Fetch the newest window so opening a long conversation never starts at
        # its oldest messages.  Reverse it for the chat UI's chronological order.
        messages = query.order_by(
            DirectMessage.created_at.desc(),
            DirectMessage.id.desc(),
        ).offset(skip).limit(limit).all()
        messages.reverse()
        unread = [message for message in messages if message.sender_id != user.id and message.read_at is None]
        if unread:
            read_at = utc_now()
            for message in unread:
                message.read_at = read_at
            queue_realtime_event(
                db,
                user_ids={conversation.user_low_id, conversation.user_high_id},
                payload={
                    "type": "messages.read",
                    "conversation_id": conversation.id,
                    "reader_id": user.id,
                    "message_ids": [message.id for message in unread],
                    "read_at": read_at.isoformat(),
                },
            )
            db.commit()
        return {
            "conversation": self._serialize_conversation(db, conversation, user.id),
            "messages": [self._serialize_message(message) for message in messages],
            "total": total,
        }

    def send(self, db: Session, *, user: User, conversation_id: int, body: str) -> dict:
        conversation = self._require_conversation(db, conversation_id, user)
        counterpart = self._counterpart(conversation, user.id)
        if self._is_blocked(db, user.id, counterpart.id):
            raise HTTPException(status_code=403, detail="Отправка сообщений недоступна")
        normalized_body = body.strip()
        if not normalized_body:
            raise HTTPException(status_code=422, detail="Сообщение не может быть пустым")
        message = DirectMessage(
            conversation_id=conversation.id,
            sender_id=user.id,
            body=normalized_body,
        )
        conversation.updated_at = utc_now()
        db.add(message)
        db.flush()
        notification_service.create(
            db,
            user_id=counterpart.id,
            notification_type="direct_message",
            title=f"Новое сообщение от {self._public_name(user)}",
            message=normalized_body[:160],
            link_url=f"/messages?with={quote(self._public_name(user), safe='')}",
            entity_type="direct_message",
            entity_id=message.id,
            commit=False,
        )
        serialized_message = self._serialize_message(message)
        serialized_message["created_at"] = (
            message.created_at.isoformat() if message.created_at else None
        )
        serialized_message["read_at"] = None
        queue_realtime_event(
            db,
            user_ids={user.id, counterpart.id},
            payload={
                "type": "message.created",
                "conversation_id": conversation.id,
                "message": serialized_message,
            },
        )
        db.commit()
        message = db.query(DirectMessage).options(joinedload(DirectMessage.sender)).filter(DirectMessage.id == message.id).first()
        return self._serialize_message(message)

    def block(self, db: Session, *, user: User, username: str) -> None:
        counterpart = self._user_by_username(db, username)
        self._pair(user.id, counterpart.id)
        exists = db.query(UserBlock).filter(
            UserBlock.blocker_id == user.id,
            UserBlock.blocked_id == counterpart.id,
        ).first()
        if exists is None:
            db.add(UserBlock(blocker_id=user.id, blocked_id=counterpart.id))
            db.commit()

    def unblock(self, db: Session, *, user: User, username: str) -> None:
        counterpart = self._user_by_username(db, username)
        block = db.query(UserBlock).filter(
            UserBlock.blocker_id == user.id,
            UserBlock.blocked_id == counterpart.id,
        ).first()
        if block is not None:
            db.delete(block)
            db.commit()

    def report(self, db: Session, *, user: User, message_id: int, reason: str) -> None:
        message = db.query(DirectMessage).options(joinedload(DirectMessage.conversation)).filter(
            DirectMessage.id == message_id
        ).first()
        if message is None or user.id not in {
            message.conversation.user_low_id,
            message.conversation.user_high_id,
        }:
            raise HTTPException(status_code=404, detail="Сообщение не найдено")
        if message.sender_id == user.id:
            raise HTTPException(status_code=400, detail="Нельзя пожаловаться на собственное сообщение")
        report = db.query(DirectMessageReport).filter(
            DirectMessageReport.message_id == message.id,
            DirectMessageReport.reporter_id == user.id,
        ).first()
        if report is None:
            db.add(DirectMessageReport(
                message_id=message.id,
                reporter_id=user.id,
                reason=reason.strip(),
            ))
        else:
            report.reason = reason.strip()
            report.status = "open"
        db.commit()


messaging_service = MessagingService()
