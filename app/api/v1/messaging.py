from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user, get_onboarded_active_user
from app.database import get_db
from app.models.user import User
from app.schemas.messaging import (
    DirectConversationResponse,
    DirectMessageCreate,
    DirectMessageListResponse,
    DirectMessageResponse,
    MessageOperationResult,
    MessageReportCreate,
)
from app.services.messaging_service import messaging_service


router = APIRouter(prefix="/messages", tags=["direct messages"])


@router.get("/conversations", response_model=list[DirectConversationResponse])
def list_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return messaging_service.list_conversations(db, user=current_user, limit=limit)


@router.post("/conversations/{username}", response_model=DirectConversationResponse)
def open_conversation(
    username: str,
    current_user: User = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    return messaging_service.get_or_create(db, user=current_user, username=username)


@router.get("/conversations/{conversation_id:int}/messages", response_model=DirectMessageListResponse)
def list_messages(
    conversation_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return messaging_service.list_messages(
        db,
        user=current_user,
        conversation_id=conversation_id,
        skip=skip,
        limit=limit,
    )


@router.post("/conversations/{conversation_id:int}/messages", response_model=DirectMessageResponse)
def send_message(
    conversation_id: int,
    payload: DirectMessageCreate,
    current_user: User = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    return messaging_service.send(
        db,
        user=current_user,
        conversation_id=conversation_id,
        body=payload.body,
    )


@router.put("/blocks/{username}", response_model=MessageOperationResult)
def block_user(
    username: str,
    current_user: User = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    messaging_service.block(db, user=current_user, username=username)
    return MessageOperationResult()


@router.delete("/blocks/{username}", response_model=MessageOperationResult)
def unblock_user(
    username: str,
    current_user: User = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    messaging_service.unblock(db, user=current_user, username=username)
    return MessageOperationResult()


@router.post("/{message_id:int}/report", response_model=MessageOperationResult)
def report_message(
    message_id: int,
    payload: MessageReportCreate,
    current_user: User = Depends(get_onboarded_active_user),
    db: Session = Depends(get_db),
):
    messaging_service.report(db, user=current_user, message_id=message_id, reason=payload.reason)
    return MessageOperationResult()
