from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user, get_onboarded_active_user
from app.core.time import utc_now
from app.database import get_db
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.clan import Clan
from app.models.cycle_diplomacy import CycleDiplomacyPair, CycleDiplomacyProposal
from app.models.user import User
from app.services.cycle_diplomacy_service import CycleDiplomacyService
from app.services.cycle_plan_service import CyclePlanService


router = APIRouter(prefix='/diplomacy', tags=['cycle-diplomacy'])
service = CycleDiplomacyService()


class DiplomaticAction(BaseModel):
    action: Literal['declare_war', 'offer_alliance', 'offer_peace', 'accept', 'revoke', 'break_alliance']
    other_clan_id: int = Field(gt=0)
    duration: int | None = Field(default=None, gt=0)
    proposal_id: int | None = Field(default=None, gt=0)
    expected_revision: int | None = Field(default=None, ge=0)


def _run(db, operation):
    try:
        return operation()
    except PermissionError as error:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error


def _cycle(db, cycle_id):
    cycle = db.get(CampaignCycleRecord, cycle_id)
    if cycle is None:
        raise ValueError('Unknown cycle')
    return cycle


def _clan(db, clan_id):
    clan = db.get(Clan, clan_id)
    return dict(id=clan_id, name=clan.name if clan and not clan.is_deleted else None,
                avatar_url=clan.avatar_url if clan and not clan.is_deleted else None)


def _private(db, cycle, clan_id, user_id):
    CyclePlanService._permission(db, clan_id, user_id)
    pairs = db.query(CycleDiplomacyPair).filter(
        CycleDiplomacyPair.season_id == cycle.season_id,
        (CycleDiplomacyPair.clan_low_id == clan_id) | (CycleDiplomacyPair.clan_high_id == clan_id),
    ).all()
    pair_by_id = {pair.id: pair for pair in pairs}
    proposals = db.query(CycleDiplomacyProposal).filter(CycleDiplomacyProposal.pair_id.in_(pair_by_id)).order_by(CycleDiplomacyProposal.id.desc()).all()
    return dict(pairs=[dict(pair_id=p.id, other_clan_id=p.clan_high_id if p.clan_low_id == clan_id else p.clan_low_id,
                           revision=p.revision) for p in pairs],
                proposals=[dict(id=p.id, sender_clan_id=p.sender_clan_id, kind=p.kind,
                                other_clan_id=pair_by_id[p.pair_id].clan_high_id if pair_by_id[p.pair_id].clan_low_id == clan_id else pair_by_id[p.pair_id].clan_low_id,
                                status=service.proposal_status(db, p, cycle=cycle, now=utc_now()),
                                first_full_cycle=p.first_full_cycle, expires_after_cycle=p.expires_after_cycle,
                                created_at=p.created_at) for p in proposals])


@router.get('/cycles/{cycle_id}')
def relations(cycle_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_active_user)):
    def action():
        cycle = _cycle(db, cycle_id)
        rows = service.public_projection(db, season_id=cycle.season_id, now=utc_now())
        return {'relations': [{**row, 'clan_low': _clan(db, row['clan_low_id']),
                               'clan_high': _clan(db, row['clan_high_id'])} for row in rows]}
    return _run(db, action)


@router.get('/cycles/{cycle_id}/clans/{clan_id}')
def proposals(cycle_id: int, clan_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return _run(db, lambda: _private(db, _cycle(db, cycle_id), clan_id, user.id))


@router.post('/cycles/{cycle_id}/clans/{clan_id}')
def diplomatic_action(cycle_id: int, clan_id: int, payload: DiplomaticAction,
                      db: Session = Depends(get_db), user: User = Depends(get_onboarded_active_user)):
    def action():
        args = dict(cycle_id=cycle_id, clan_id=clan_id, other_clan_id=payload.other_clan_id,
                    actor_user_id=user.id, now=utc_now(), expected_revision=payload.expected_revision)
        if payload.action == 'declare_war':
            service.declare_war(db, duration=payload.duration, **args)
        elif payload.action in ('offer_alliance', 'offer_peace'):
            service.offer(db, kind='alliance' if payload.action == 'offer_alliance' else 'peace', **args)
        elif payload.action in ('accept', 'revoke'):
            getattr(service, payload.action)(db, proposal_id=payload.proposal_id, **args)
        else:
            service.break_alliance(db, **args)
        db.commit()
        return _private(db, _cycle(db, cycle_id), clan_id, user.id)
    return _run(db, action)
