from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.core.auth import get_current_active_user, get_current_admin_user
from app.database import get_db
from app.models.user import User
from app.schemas.feedback import (
    FeedbackAdminUpdate,
    FeedbackListResponse,
    FeedbackReplyCreate,
    FeedbackTicketCreate,
    FeedbackTicketResponse,
)
from app.services.feedback_service import feedback_service
from app.utils.image_processor import process_feedback_image


router = APIRouter(prefix="/feedback", tags=["feedback"])
admin_router = APIRouter(prefix="/admin/feedback", tags=["admin feedback"])
MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024


async def _save_screenshot(image: UploadFile | None) -> str | None:
    if image is None or not image.filename:
        return None
    if not (image.content_type or "").lower().startswith("image/"):
        raise HTTPException(status_code=400, detail="Вложение должно быть изображением")
    content = await image.read(MAX_SCREENSHOT_BYTES + 1)
    if not content:
        return None
    if len(content) > MAX_SCREENSHOT_BYTES:
        raise HTTPException(status_code=400, detail="Скриншот не должен превышать 8 МБ")
    directory = Path(settings.UPLOAD_DIR) / "feedback"
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"feedback_{uuid4().hex}.webp"
    path = directory / filename
    try:
        process_feedback_image(content, str(path))
    except Exception as error:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Не удалось обработать скриншот") from error
    return f"/images/feedback/{filename}"


@router.post("/tickets", response_model=FeedbackTicketResponse, status_code=201)
async def create_ticket(
    category: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    reproduction_steps: str | None = Form(None),
    expected_result: str | None = Form(None),
    actual_result: str | None = Form(None),
    source_path: str | None = Form(None),
    user_agent: str | None = Form(None),
    image: UploadFile | None = File(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        payload = FeedbackTicketCreate(
            category=category,
            title=title,
            description=description,
            reproduction_steps=reproduction_steps,
            expected_result=expected_result,
            actual_result=actual_result,
            source_path=source_path,
            user_agent=user_agent,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    attachment_url = await _save_screenshot(image)
    try:
        return feedback_service.create(
            db,
            reporter=current_user,
            data=payload,
            attachment_url=attachment_url,
        )
    except Exception:
        if attachment_url:
            (Path(settings.UPLOAD_DIR) / attachment_url.removeprefix("/images/")).unlink(missing_ok=True)
        raise


@router.get("/tickets", response_model=list[FeedbackTicketResponse])
def list_my_tickets(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return feedback_service.list_for_user(db, user=current_user)


@router.get("/tickets/{ticket_id:int}", response_model=FeedbackTicketResponse)
def get_my_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        return feedback_service.get_for_user(db, ticket_id=ticket_id, user=current_user)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/tickets/{ticket_id:int}/replies", response_model=FeedbackTicketResponse)
def reply_to_ticket(
    ticket_id: int,
    payload: FeedbackReplyCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        return feedback_service.add_user_reply(
            db,
            ticket_id=ticket_id,
            user=current_user,
            body=payload.body,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@admin_router.get("/tickets", response_model=FeedbackListResponse)
def list_admin_tickets(
    status: str | None = Query(None),
    category: str | None = Query(None),
    priority: str | None = Query(None),
    search: str | None = Query(None, max_length=160),
    limit: int = Query(200, ge=1, le=500),
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    return feedback_service.list_admin(
        db,
        status=status,
        category=category,
        priority=priority,
        search=search,
        limit=limit,
    )


@admin_router.get("/tickets/{ticket_id:int}", response_model=FeedbackTicketResponse)
def get_admin_ticket(
    ticket_id: int,
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    try:
        return feedback_service.payload(feedback_service.get_admin(db, ticket_id=ticket_id))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@admin_router.post("/tickets/{ticket_id:int}/read", response_model=FeedbackTicketResponse)
def mark_admin_ticket_read(
    ticket_id: int,
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    try:
        return feedback_service.mark_admin_read(db, ticket_id=ticket_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@admin_router.patch("/tickets/{ticket_id:int}", response_model=FeedbackTicketResponse)
def update_admin_ticket(
    ticket_id: int,
    payload: FeedbackAdminUpdate,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    try:
        return feedback_service.admin_update(
            db,
            ticket_id=ticket_id,
            admin=current_admin,
            data=payload,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@admin_router.post("/tickets/{ticket_id:int}/replies", response_model=FeedbackTicketResponse)
def reply_as_admin(
    ticket_id: int,
    payload: FeedbackReplyCreate,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    try:
        return feedback_service.admin_reply(
            db,
            ticket_id=ticket_id,
            admin=current_admin,
            body=payload.body,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
