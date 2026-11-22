"""Authenticated barter API; settlement hooks deliberately have no routes.

Mounted beneath /api/v1/campaign/cycles, like the economy/diplomacy routers.
Manual trading is allowed in every phase except season_ended. Offer expiry
is defined by the service's first two full cycles, never a wall-clock TTL.
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user, get_onboarded_active_user
from app.core.time import as_utc, utc_now
from app.database import get_db
from app.models.cycle_market import CycleMarketCaravan, CycleMarketOffer
from app.models.user import User
from app.services.cycle_diplomacy_service import _cursor
from app.services.cycle_economy import Resources
from app.services.cycle_market_service import CycleMarketService
from app.services.cycle_plan_service import CyclePlanService


router = APIRouter(prefix='/market', tags=['cycle-market'])
service = CycleMarketService()
Amount = Annotated[Decimal, Field(ge=0, max_digits=24, decimal_places=6)]
Revision = Annotated[int, Field(strict=True, ge=0)]


class CargoInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    iron: Amount = Decimal(0)
    wood: Amount = Decimal(0)
    food: Amount = Decimal(0)
    mithril: Amount = Decimal(0)

    def resources(self):
        return Resources(**self.model_dump())


class CommandInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    command_id: str = Field(min_length=1, max_length=128)
    expected_wallet_revision: Revision

    @field_validator('command_id')
    @classmethod
    def nonblank_command(cls, value):
        if not value.strip():
            raise ValueError('Nonempty command ID required')
        return value


class CreateInput(CommandInput):
    offered: CargoInput
    requested: CargoInput
    target_clan_id: int | None = Field(default=None, gt=0)


class CancelInput(CommandInput):
    expected_revision: Revision


class AcceptInput(CancelInput):
    expected_sender_revision: Revision


def _run(db, operation):
    try:
        return operation()
    except PermissionError as error:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(error)) from error
    except (ValueError, IntegrityError) as error:
        db.rollback()
        detail = 'Concurrent market update; retry the same command' if isinstance(error, IntegrityError) else str(error)
        raise HTTPException(status_code=409, detail=detail) from error
    except Exception:
        db.rollback()
        raise


def _offer(row, cycle, now):
    status = row.status
    if status == 'pending' and _cursor(cycle, now) > row.expires_after_cycle:
        status = 'expired'
    return dict(id=row.id, season_id=row.season_id, sender_clan_id=row.sender_clan_id,
                target_clan_id=row.target_clan_id, accepter_clan_id=row.accepter_clan_id,
                offered=dict(row.offered), requested=dict(row.requested), status=status,
                revision=row.revision, first_full_cycle=row.first_full_cycle,
                expires_after_cycle=row.expires_after_cycle, created_at=as_utc(row.created_at),
                accepted_at=as_utc(row.accepted_at) if row.accepted_at else None)


@router.get('/cycles/{cycle_id}')
def marketplace(cycle_id: int, db: Session = Depends(get_db),
                _user: User = Depends(get_current_active_user)):
    def action():
        now = utc_now()
        cycle, _, _ = service._context(db, cycle_id, now, manual=False)
        rows = db.query(CycleMarketOffer).filter_by(
            season_id=cycle.season_id, target_clan_id=None, status='pending'
        ).order_by(CycleMarketOffer.id).all()
        offers = [_offer(row, cycle, now) for row in rows]
        return {'offers': [row for row in offers if row['status'] == 'pending']}
    return _run(db, action)


@router.get('/cycles/{cycle_id}/clans/{clan_id}')
def clan_market(cycle_id: int, clan_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_active_user)):
    def action():
        CyclePlanService._permission(db, clan_id, user.id)
        now = utc_now()
        cycle, _, _ = service._context(db, cycle_id, now, manual=False)
        rows = db.query(CycleMarketOffer).filter(
            CycleMarketOffer.season_id == cycle.season_id,
            (CycleMarketOffer.sender_clan_id == clan_id) |
            (CycleMarketOffer.target_clan_id == clan_id) |
            (CycleMarketOffer.accepter_clan_id == clan_id),
        ).order_by(CycleMarketOffer.id).all()
        caravans = db.query(CycleMarketCaravan).join(
            CycleMarketOffer, CycleMarketOffer.id == CycleMarketCaravan.offer_id
        ).filter(CycleMarketOffer.season_id == cycle.season_id,
                 CycleMarketCaravan.recipient_clan_id == clan_id).order_by(CycleMarketCaravan.id).all()
        return dict(offers=[_offer(row, cycle, now) for row in rows], caravans=[dict(
            id=c.id, offer_id=c.offer_id, recipient_clan_id=c.recipient_clan_id,
            cargo=dict(c.cargo), route=dict(c.route), departed_at=as_utc(c.departed_at),
            arrives_at=as_utc(c.arrives_at),
            delivered_at=as_utc(c.delivered_at) if c.delivered_at else None, revision=c.revision,
        ) for c in caravans])
    return _run(db, action)


def _mutate(db, cycle_id, clan_id, user_id, payload, operation, offer_id=None):
    def action():
        now = utc_now()
        args = payload.model_dump(exclude={'offered', 'requested'})
        if isinstance(payload, CreateInput):
            args.update(offered=payload.offered.resources(), requested=payload.requested.resources())
        if offer_id is not None:
            args['offer_id'] = offer_id
        row = operation(db, cycle_id=cycle_id, clan_id=clan_id, actor_id=user_id, now=now, **args)
        cycle, _, _ = service._context(db, cycle_id, now, manual=False)
        result = _offer(row, cycle, now)
        db.commit()
        return result
    return _run(db, action)


@router.post('/cycles/{cycle_id}/clans/{clan_id}/offers')
def create_offer(cycle_id: int, clan_id: int, payload: CreateInput,
                 db: Session = Depends(get_db), user: User = Depends(get_onboarded_active_user)):
    return _mutate(db, cycle_id, clan_id, user.id, payload, service.create)


@router.post('/cycles/{cycle_id}/clans/{clan_id}/offers/{offer_id}/accept')
def accept_offer(cycle_id: int, clan_id: int, offer_id: int, payload: AcceptInput,
                 db: Session = Depends(get_db), user: User = Depends(get_onboarded_active_user)):
    return _mutate(db, cycle_id, clan_id, user.id, payload, service.accept, offer_id)


@router.get('/cycles/{cycle_id}/clans/{clan_id}/offers/{offer_id}/quote')
def acceptance_quote(cycle_id: int, clan_id: int, offer_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_onboarded_active_user)):
    def action():
        CyclePlanService._permission(db, clan_id, user.id)
        return service.quote(db, cycle_id=cycle_id, offer_id=offer_id, clan_id=clan_id, actor_id=user.id, now=utc_now())
    return _run(db, action)


@router.post('/cycles/{cycle_id}/clans/{clan_id}/offers/{offer_id}/cancel')
def cancel_offer(cycle_id: int, clan_id: int, offer_id: int, payload: CancelInput,
                 db: Session = Depends(get_db), user: User = Depends(get_onboarded_active_user)):
    return _mutate(db, cycle_id, clan_id, user.id, payload, service.cancel, offer_id)
