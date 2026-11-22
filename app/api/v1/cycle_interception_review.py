"""Административный пересмотр перехватов; подключается родительским приложением."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user
from app.database import get_db
from app.models.user import User
from app.services.cycle_interception_review_service import CycleInterceptionReviewService


class ReviewRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def checked(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                raise HTTPException(409, 'Некорректные параметры пересмотра перехвата') from error
        return checked


router = APIRouter(tags=['cycle-interception-review'], route_class=ReviewRoute)
service = CycleInterceptionReviewService()
Database = Annotated[Session, Depends(get_db)]
Admin = Annotated[User, Depends(get_current_admin_user)]
CycleId = Annotated[int, Path(gt=0)]
DispatchId = Annotated[str, Query(min_length=1, max_length=120)]
Positive = Annotated[int, Field(strict=True, gt=0)]
TextId = Annotated[str, Field(strict=True, min_length=1, max_length=120)]


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    command_id: TextId
    expected_revision: Positive
    reason: Annotated[str, Field(strict=True, min_length=1, max_length=500)]

    @field_validator('command_id', 'reason')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('Требуется непустое значение')
        return value.strip()


class ContributionInput(Command):
    replay_id: TextId
    user_id: Positive
    counted: Annotated[bool, Field(strict=True)]


class AdjustmentInput(Command):
    side_clan_id: Positive
    amount: Decimal = Field(allow_inf_nan=False, max_digits=28, decimal_places=12)


class ConfirmInput(Command):
    preview_command_id: TextId


def _run(db, action):
    try:
        result = action()
        db.commit()
        return result
    except ValueError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, 'Параллельное изменение; обновите данные и повторите действие') from error


@router.get('/{cycle_id}/interception/review')
def read(cycle_id: CycleId, dispatch_id: DispatchId, db: Database, _admin: Admin):
    return _run(db, lambda: service.read(db, cycle_id=cycle_id, dispatch_id=dispatch_id))


def _command(db, user, cycle_id, dispatch_id, payload, method):
    return _run(db, lambda: method(db, cycle_id=cycle_id, dispatch_id=dispatch_id,
        actor_user_id=user.id, **payload.model_dump()))


@router.post('/{cycle_id}/interception/review/contributions')
def review(cycle_id: CycleId, dispatch_id: DispatchId, payload: ContributionInput, db: Database, admin: Admin):
    return _command(db, admin, cycle_id, dispatch_id, payload, service.review_contribution)


@router.post('/{cycle_id}/interception/review/adjustments')
def adjust(cycle_id: CycleId, dispatch_id: DispatchId, payload: AdjustmentInput, db: Database, admin: Admin):
    return _command(db, admin, cycle_id, dispatch_id, payload, service.adjust)


@router.post('/{cycle_id}/interception/review/outcome/preview')
def preview(cycle_id: CycleId, dispatch_id: DispatchId, payload: Command, db: Database, admin: Admin):
    return _command(db, admin, cycle_id, dispatch_id, payload, service.preview_outcome)


@router.post('/{cycle_id}/interception/review/outcome/confirm')
def confirm(cycle_id: CycleId, dispatch_id: DispatchId, payload: ConfirmInput, db: Database, admin: Admin):
    return _command(db, admin, cycle_id, dispatch_id, payload, service.confirm_outcome)
