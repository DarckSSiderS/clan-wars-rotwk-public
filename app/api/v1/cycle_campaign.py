from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user, get_current_admin_user, get_onboarded_active_user
from app.core.campaign_mode import interseason_season
from app.core.time import utc_now
from app.database import get_db
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.clan import Clan
from app.models.cycle_battle import CycleTerritoryBattle, CycleMatchContribution, CycleScoreAdjustment, CycleOwnershipCorrection
from app.models.territory import Territory
from app.models.user import User
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.cycle_orders import Order
from app.services.cycle_plan_service import CyclePlanService
from app.services.cycle_battle_service import CycleBattleService
from app.services.cycle_ownership_service import CycleOwnershipService
from app.services.cycle_battle_match_view import battle_match_summaries


router = APIRouter(prefix='/cycles', tags=['campaign-cycles'])
from app.api.v1.cycle_economy import router as economy_router
from app.api.v1.cycle_diplomacy import router as diplomacy_router
from app.api.v1.cycle_market import router as market_router
from app.api.v1.cycle_operations import router as operations_router
from app.api.v1.cycle_interception_review import router as interception_review_router
from app.api.v1.cycle_administration import router as administration_router

router.include_router(economy_router)
router.include_router(diplomacy_router)
router.include_router(market_router)
router.include_router(operations_router)
router.include_router(interception_review_router)
router.include_router(administration_router)
cycles = CampaignCycleStore()
plans = CyclePlanService()
battles = CycleBattleService()


class OrderInput(BaseModel):
    user_id: int = Field(gt=0)
    kind: Literal['attack', 'defend', 'reserve', 'ambush']
    territory_id: int | None = Field(default=None, gt=0)
    source_id: int | None = Field(default=None, gt=0)
    route: Literal['land', 'sea'] = 'land'


class PlanInput(BaseModel):
    expected_revision: int = Field(ge=0)
    orders: list[OrderInput] = Field(max_length=500)


class ScoreAdjustmentInput(BaseModel):
    clan_id: int = Field(gt=0)
    amount: Decimal = Field(max_digits=28, decimal_places=12)
    command_id: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)


class MatchReviewInput(BaseModel):
    replay_id: str = Field(min_length=1, max_length=120)
    user_id: int = Field(gt=0)
    counted: bool
    reason: str = Field(min_length=1, max_length=500)


class OwnershipCorrectionInput(BaseModel):
    new_owner_clan_id: int | None = Field(gt=0)
    preview_token: str = Field(pattern=r'^[0-9a-f]{64}$')
    command_id: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)


class LateReplayDecisionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preview_token: str = Field(pattern=r'^[0-9a-f]{64}$')
    counted: bool = Field(strict=True)
    command_id: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)


def _battle_detail(db, row):
    calculation_fields = {'historical_elo', 'patch_family', 'started_at', 'finished_at',
        'base_points', 'victory_bonus_percent', 'direct_multiplier', 'exhaustion_multiplier'}
    territory = db.get(Territory, row.territory_id)
    scores = battles.scores(db, row.id)
    contributions = db.query(CycleMatchContribution).filter_by(battle_id=row.id).order_by(CycleMatchContribution.id).all()
    sides = []
    for side in row.sides:
        clan = db.get(Clan, side['clan_id'])
        member_ids = set(side['user_ids']) | {r.user_id for r in contributions if r.clan_id == side['clan_id']}
        members = db.query(User).filter(User.id.in_(member_ids)).order_by(User.id).all()
        sides.append(dict(clan_id=side['clan_id'],
                          clan_name=clan.name if clan and not clan.is_deleted else None,
                          avatar_url=clan.avatar_url if clan and not clan.is_deleted else None,
                          score=str(scores[side['clan_id']]),
                          role='defense' if side['clan_id'] == row.owner_clan_id else 'attack',
                          members=[{'user_id': u.id, 'username': u.username, 'display_name': u.display_name}
                                   for u in members]))
    adjustments = db.query(CycleScoreAdjustment).filter_by(battle_id=row.id).order_by(CycleScoreAdjustment.id).all()
    corrections = db.query(CycleOwnershipCorrection).filter_by(battle_id=row.id).order_by(CycleOwnershipCorrection.id).all()
    owner = db.get(Clan, territory.owner_clan_id) if territory and territory.owner_clan_id is not None else None
    original_owner = db.get(Clan, row.owner_clan_id) if row.owner_clan_id is not None else None
    return dict(id=row.id, cycle_id=row.cycle_id, territory_id=row.territory_id,
                territory_name=territory.name if territory else None, sides=sides,
                owner_clan_id=row.owner_clan_id,
                owner_clan_name=original_owner.name if original_owner and not original_owner.is_deleted else None,
                matches=battle_match_summaries(db, contributions),
                winner_clan_id=row.winner_clan_id,
                recalculated_winner_clan_id=row.recalculated_winner_clan_id,
                completed_at=row.completed_at,
                ownership_applied_at=row.ownership_applied_at,
                current_owner_clan_id=territory.owner_clan_id if territory else None,
                current_owner_name=owner.name if owner and not owner.is_deleted else None,
                ownership_corrections=[dict(id=r.id, previous_owner_clan_id=r.previous_owner_clan_id,
                    new_owner_clan_id=r.new_owner_clan_id, reason=r.reason, applied_at=r.applied_at) for r in corrections],
                contributions=[dict(replay_id=r.replay_id, user_id=r.user_id, clan_id=r.clan_id,
                                    points=str(r.points), counted=r.counted, reason=r.reason,
                                    review_reason=r.review_reason,
                                    calculation={key: value for key, value in r.calculation.items()
                                        if key in calculation_fields} if isinstance(r.calculation, dict) else None)
                               for r in contributions],
                adjustments=[dict(id=r.id, clan_id=r.clan_id, points=str(r.points), reason=r.reason) for r in adjustments])


def _status(row):
    timeline = cycles.timeline(row)
    now = utc_now()
    return dict(id=row.id, season_id=row.season_id, number=row.number,
                rule_version=row.rule_version,
                phase=timeline.phase_at(now).value if now >= timeline.starts_at else 'scheduled',
                starts_at=timeline.starts_at, preparation_at=timeline.preparation_at,
                battle_at=timeline.battle_at, battle_ends_at=timeline.battle_ends_at,
                replay_deadline=timeline.replay_deadline, settled_at=timeline.settled_at,
                next_cycle_starts_at=timeline.next_cycle_starts_at,
                season_end_requested=timeline.season_end_requested, server_time=now)


def _translate(db, action):
    try:
        return action()
    except PermissionError as error:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(error)) from error
    except CycleConflict as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get('/current')
def current_cycle(db: Session = Depends(get_db),
                  _user: User = Depends(get_current_active_user)):
    season = db.query(CampaignSeason).filter_by(status='active').order_by(CampaignSeason.number.desc()).first()
    if season is None:
        season = db.query(CampaignSeason).order_by(CampaignSeason.number.desc()).first()
    mode = (season.rules_snapshot or {}).get('mechanics_version', 'legacy') if season else 'legacy'
    row = db.query(CampaignCycleRecord).filter_by(season_id=season.id).order_by(CampaignCycleRecord.number.desc()).first() if season and mode == 'cycle_v1' else None
    status = _status(row) if row else None
    visible = bool(row and season.status == 'active' and row.orders_frozen_at is not None
                   and row.battles_registered and status['phase'] in {'battle', 'replay_loading', 'settlement'})
    links = db.query(CycleTerritoryBattle).filter_by(cycle_id=row.id).order_by(CycleTerritoryBattle.territory_id).all() if visible else []
    archived = interseason_season(db)
    return dict(mechanics_version=mode, season_id=season.id if season else None,
                interseason=archived is not None,
                archived_season_id=archived.id if archived else None,
                season_status=season.status if season else None, cycle=status,
                territory_battles=[dict(battle_id=b.id, territory_id=b.territory_id) for b in links])


@router.get('/{cycle_id}')
def cycle_status(cycle_id: int, db: Session = Depends(get_db),
                 _user: User = Depends(get_current_active_user)):
    row = db.get(CampaignCycleRecord, cycle_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Cycle not found')
    return _status(row)


@router.post('/seasons/{season_id}/start')
def start_cycle(season_id: int, db: Session = Depends(get_db),
                _admin: User = Depends(get_current_admin_user)):
    def action():
        row = cycles.start(db, season_id=season_id)
        db.commit()
        return _status(row)
    return _translate(db, action)


@router.get('/{cycle_id}/clans/{clan_id}/plan')
def get_plan(cycle_id: int, clan_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_active_user)):
    return _translate(db, lambda: plans.read(db, cycle_id=cycle_id, clan_id=clan_id, actor_user_id=user.id))


@router.put('/{cycle_id}/clans/{clan_id}/plan')
def save_plan(cycle_id: int, clan_id: int, payload: PlanInput, db: Session = Depends(get_db),
              user: User = Depends(get_onboarded_active_user)):
    def action():
        plans.save(db, cycle_id=cycle_id, clan_id=clan_id, actor_user_id=user.id,
                   expected_revision=payload.expected_revision,
                   orders=[Order(**item.model_dump()) for item in payload.orders], now=utc_now())
        db.commit()
        return plans.read(db, cycle_id=cycle_id, clan_id=clan_id, actor_user_id=user.id)
    return _translate(db, action)


@router.get('/{cycle_id}/clans/{clan_id}/planning')
def planning_context(cycle_id: int, clan_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_active_user)):
    return _translate(db, lambda: plans.planning(db, cycle_id=cycle_id, clan_id=clan_id,
                                               actor_user_id=user.id, now=utc_now()))


@router.post('/{cycle_id}/request-season-end')
def request_season_end(cycle_id: int, db: Session = Depends(get_db),
                       _admin: User = Depends(get_current_admin_user)):
    def action():
        row = cycles.request_end(db, cycle_id=cycle_id)
        db.commit()
        return _status(row)
    return _translate(db, action)


@router.get('/{cycle_id}/battles')
def cycle_battles(cycle_id: int, db: Session = Depends(get_db),
                  _user: User = Depends(get_current_active_user)):
    if db.get(CampaignCycleRecord, cycle_id) is None:
        raise HTTPException(status_code=404, detail='Cycle not found')
    rows = db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle_id).order_by(CycleTerritoryBattle.territory_id).all()
    return {'battles': [_battle_detail(db, row) for row in rows]}


@router.get('/{cycle_id}/map')
def cycle_map(cycle_id: int, db: Session = Depends(get_db),
              user: User = Depends(get_current_active_user)):
    from app.services.cycle_map_service import CycleMapService
    return _translate(db, lambda: CycleMapService().read(db, cycle_id=cycle_id, actor_user_id=user.id, now=utc_now()))


@router.get('/battles/{battle_id}')
def battle_detail(battle_id: int, db: Session = Depends(get_db),
                  _user: User = Depends(get_current_active_user)):
    row = db.get(CycleTerritoryBattle, battle_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Battle not found')
    return _battle_detail(db, row)


@router.get('/battles/{battle_id}/late-replays')
def late_replays(battle_id: int, after_id: int = Query(default=0, ge=0),
                 limit: int = Query(default=200, ge=1, le=500), db: Session = Depends(get_db),
                 _admin: User = Depends(get_current_admin_user)):
    from app.services.cycle_late_replay_service import CycleLateReplayService
    return _translate(db, lambda: CycleLateReplayService().read(db, battle_id=battle_id,
        after_id=after_id, limit=limit))


@router.get('/battles/{battle_id}/late-replays/{match_id}')
def preview_late_replay(battle_id: int, match_id: int, db: Session = Depends(get_db),
                        _admin: User = Depends(get_current_admin_user)):
    from app.services.cycle_late_replay_review_service import CycleLateReplayReviewService
    return _translate(db, lambda: CycleLateReplayReviewService().preview(db,
        battle_id=battle_id, match_id=match_id))


@router.post('/battles/{battle_id}/late-replays/{match_id}')
def decide_late_replay(battle_id: int, match_id: int, payload: LateReplayDecisionInput,
                       db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    from app.services.cycle_late_replay_review_service import CycleLateReplayReviewService
    def action():
        CycleLateReplayReviewService().decide(db, battle_id=battle_id, match_id=match_id,
            actor_user_id=admin.id, now=utc_now(), **payload.model_dump())
        db.commit()
        return _battle_detail(db, db.get(CycleTerritoryBattle, battle_id))
    return _translate(db, action)


@router.post('/battles/{battle_id}/adjustments')
def adjust_score(battle_id: int, payload: ScoreAdjustmentInput, db: Session = Depends(get_db),
                 admin: User = Depends(get_current_admin_user)):
    def action():
        battles.adjust(db, battle_id=battle_id, clan_id=payload.clan_id, amount=payload.amount,
                       command_id=payload.command_id, actor_user_id=admin.id, reason=payload.reason)
        db.commit()
        return _battle_detail(db, db.get(CycleTerritoryBattle, battle_id))
    return _translate(db, action)


@router.post('/battles/{battle_id}/review')
def review_match(battle_id: int, payload: MatchReviewInput, db: Session = Depends(get_db),
                 admin: User = Depends(get_current_admin_user)):
    def action():
        battles.review_contribution(db, battle_id=battle_id, replay_id=payload.replay_id,
                                    user_id=payload.user_id, counted=payload.counted,
                                    actor_user_id=admin.id, reason=payload.reason)
        db.commit()
        return _battle_detail(db, db.get(CycleTerritoryBattle, battle_id))
    return _translate(db, action)


@router.get('/battles/{battle_id}/ownership')
def preview_ownership(battle_id: int, db: Session = Depends(get_db),
                      _admin: User = Depends(get_current_admin_user)):
    return _translate(db, lambda: CycleOwnershipService().preview_correction(db, battle_id=battle_id))


@router.post('/battles/{battle_id}/ownership')
def correct_ownership(battle_id: int, payload: OwnershipCorrectionInput, db: Session = Depends(get_db),
                      admin: User = Depends(get_current_admin_user)):
    def action():
        CycleOwnershipService().correct_ownership(db, battle_id=battle_id, **payload.model_dump(),
            actor_user_id=admin.id, now=utc_now())
        db.commit()
        return _battle_detail(db, db.get(CycleTerritoryBattle, battle_id))
    return _translate(db, action)
