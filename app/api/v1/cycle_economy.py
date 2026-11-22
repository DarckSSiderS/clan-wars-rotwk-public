from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user, get_onboarded_active_user
from app.core.time import utc_now
from app.database import get_db
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.cycle_economy import CycleEconomyState, CycleEconomySnapshot
from app.models.user import User
from app.models.campaign import CampaignSeason
from app.models.clan import ClanMember
from app.models.territory import Territory
from app.models.cycle_economy import CycleTerritoryUpgrade
from app.services import cycle_economy as rules
from app.services.cycle_economy import RELICS, RESOURCE_NAMES
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_income_service import CycleIncomeService
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_plan_service import CyclePlanService


router = APIRouter(prefix='/economy', tags=['cycle-economy'])
store = CycleEconomyStore()


class RevisionInput(BaseModel):
    expected_revision: int = Field(gt=0)


class RelicSelectionInput(RevisionInput):
    selected: list[str] = Field(max_length=4)


class RelicPurchaseInput(RevisionInput):
    key: str = Field(min_length=1, max_length=80)


class ActiveSelectionInput(RelicSelectionInput):
    cycle_id: int = Field(gt=0)


class MarketInput(RevisionInput):
    resource: Literal['iron', 'wood', 'food', 'mithril']
    quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=6)
    buying: bool


class UpgradeInput(RevisionInput):
    territory_id: int = Field(gt=0)
    branch: Literal['gold', 'profile', 'mithril', 'fortification', 'offense', 'naval']
    expected_upgrade_revision: int = Field(ge=0)


def _serialize(state):
    return dict(state_id=state.id, season_id=state.season_id, clan_id=state.clan_id,
                revision=state.revision, wallet=dict(state.wallet), relics=dict(state.relics),
                active_relics=list(state.active_relics), starters_chosen=state.starters_chosen)


def _run(db, operation):
    try:
        return operation()
    except PermissionError as error:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error


def _state(db, season_id, clan_id, user_id):
    CyclePlanService._permission(db, clan_id, user_id)
    row = db.query(CycleEconomyState).filter_by(season_id=season_id, clan_id=clan_id).one_or_none()
    if row is None:
        raise ValueError('Seasonal economy has not been initialized')
    return row


def _require_snapshot(db, state, now):
    cycle = db.query(CampaignCycleRecord).filter_by(season_id=state.season_id).order_by(CampaignCycleRecord.number.desc()).first()
    if cycle and cycle.settled_at is None and now >= CampaignCycleStore.timeline(cycle).battle_at:
        snapshot = db.query(CycleEconomySnapshot.id).filter_by(cycle_id=cycle.id, state_id=state.id).first()
        if snapshot is None:
            raise ValueError('Reveal snapshot must be frozen before post-reveal changes')


@router.get('/catalog')
def catalog(_user: User = Depends(get_current_active_user)):
    return {'relics': [dict(key=key, name=relic.name, effect=relic.effect,
                            effects=[str(value) for value in relic.effects],
                            costs=[{name: str(getattr(cost, name)) for name in RESOURCE_NAMES} for cost in relic.costs])
                       for key, relic in RELICS.items()]}


@router.get('/seasons/{season_id}/clans/{clan_id}')
def get_economy(season_id: int, clan_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_active_user)):
    def action():
        now = utc_now()
        state = _state(db, season_id, clan_id, user.id)
        with store._atomic(db):
            CycleIncomeService()._cycles(db, season_id)
            _require_snapshot(db, state, now)
            CycleIncomeService().accrue(db, state_id=state.id, now=now)
        db.commit()
        return _serialize(state)
    return _run(db, action)


@router.post('/seasons/{season_id}/clans/{clan_id}/initialize')
def initialize(season_id: int, clan_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_onboarded_active_user)):
    def action():
        CyclePlanService._permission(db, clan_id, user.id, edit=True)
        row = store.ensure_state(db, season_id=season_id, clan_id=clan_id)
        db.commit()
        return _serialize(row)
    return _run(db, action)


@router.get('/seasons/{season_id}/clans/{clan_id}/context')
def economy_context(season_id: int, clan_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_active_user)):
    def action():
        clan = CyclePlanService._permission(db, clan_id, user.id)
        season = db.get(CampaignSeason, season_id)
        if season is None or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
            raise ValueError('Cycle season required')
        cycle = db.query(CampaignCycleRecord).filter_by(season_id=season_id).order_by(CampaignCycleRecord.number.desc()).first()
        now = utc_now()
        phase = CampaignCycleStore.timeline(cycle).phase_at(now).value if cycle and now >= CampaignCycleStore.timeline(cycle).starts_at else 'scheduled'
        member = db.query(ClanMember).filter_by(clan_id=clan_id, user_id=user.id).one()
        allowed = season.status == 'active' and user.onboarding_completed_at is not None
        head = allowed and clan.leader_id == user.id
        state = db.query(CycleEconomyState).filter_by(season_id=season_id, clan_id=clan_id).one_or_none()
        result = dict(season_id=season_id, cycle_id=cycle.id if cycle else None, clan_id=clan_id,
                      clan_name=clan.name, phase=phase, server_time=now, ready=state is not None,
                      can_manage=bool(head), can_trade=bool(allowed and (head or member.is_trader)),
                      can_select=bool(head and phase in ('preparation', 'rest')),
                      state=None, catalog=catalog(user)['relics'], lands=[],
                      market_buy={k: str(v) for k, v in rules.MARKET_BUY.items()},
                      market_sell={k: str(v) for k, v in rules.MARKET_SELL.items()})
        if state is None:
            return result
        result['state'] = get_economy(season_id, clan_id, db, user)
        snapshot = store.upgrade_effects(db, state)
        for land in db.query(Territory).filter_by(owner_clan_id=clan_id, is_playable=True).order_by(Territory.id):
            upgrade = db.get(CycleTerritoryUpgrade, (season_id, land.id))
            levels = dict(upgrade.levels) if upgrade else {}
            quotes = {}
            for branch, definition in rules.UPGRADES.items():
                level = levels.get(branch, 0)
                eligible = (branch != 'naval' or land.has_port) and (branch != 'profile' or (land.resource_type in ('iron', 'wood', 'food') and (land.resource_output or 0) > 0)) and (branch != 'mithril' or (land.resource_type == 'mithril' and (land.resource_output or 0) > 0))
                cost = rules.upgrade_cost(branch, level, snapshot) if eligible and level < 3 else None
                quotes[branch] = dict(level=level, next_effect=str(definition.effects[level]) if level < 3 else None,
                                     cost=store._wallet(cost) if cost else None)
            result['lands'].append(dict(territory_id=land.id, name=land.name, revision=upgrade.revision if upgrade else 0, quotes=quotes))
        return result
    return _run(db, action)


def _mutate(db, season_id, clan_id, user_id, expected_revision, operation):
    def action():
        now = utc_now()
        with store._atomic(db):
            # Keep the same cycle -> season -> wallet order as reveal/income.
            CycleIncomeService()._cycles(db, season_id)
            state = _state(db, season_id, clan_id, user_id)
            state = store._state(db, state.id, expected_revision)
            _require_snapshot(db, state, now)
            CycleIncomeService().accrue(db, state_id=state.id, now=now)
            result = operation(state, now)
        db.commit()
        return _serialize(result)
    return _run(db, action)


@router.post('/seasons/{season_id}/clans/{clan_id}/starters')
def choose_starters(season_id: int, clan_id: int, payload: RelicSelectionInput,
                    db: Session = Depends(get_db), user: User = Depends(get_onboarded_active_user)):
    return _mutate(db, season_id, clan_id, user.id, payload.expected_revision, lambda state, now: store.choose_starters(
        db, state_id=state.id, actor_id=user.id, selected=payload.selected, expected_revision=state.revision))


@router.post('/seasons/{season_id}/clans/{clan_id}/relics')
def purchase_relic(season_id: int, clan_id: int, payload: RelicPurchaseInput,
                   db: Session = Depends(get_db), user: User = Depends(get_onboarded_active_user)):
    return _mutate(db, season_id, clan_id, user.id, payload.expected_revision, lambda state, now: store.buy_relic(
        db, state_id=state.id, actor_id=user.id, key=payload.key, expected_revision=state.revision))


@router.put('/seasons/{season_id}/clans/{clan_id}/active-relics')
def select_relics(season_id: int, clan_id: int, payload: ActiveSelectionInput,
                  db: Session = Depends(get_db), user: User = Depends(get_onboarded_active_user)):
    return _mutate(db, season_id, clan_id, user.id, payload.expected_revision, lambda state, now: store.select_active(
        db, state_id=state.id, actor_id=user.id, cycle_id=payload.cycle_id, now=now,
        selected=payload.selected, expected_revision=state.revision))


@router.post('/seasons/{season_id}/clans/{clan_id}/upgrades')
def upgrade_land(season_id: int, clan_id: int, payload: UpgradeInput,
                 db: Session = Depends(get_db), user: User = Depends(get_onboarded_active_user)):
    return _mutate(db, season_id, clan_id, user.id, payload.expected_revision, lambda state, now: store.buy_upgrade(
        db, state_id=state.id, actor_id=user.id, territory_id=payload.territory_id,
        branch=payload.branch, expected_revision=state.revision,
        expected_upgrade_revision=payload.expected_upgrade_revision))


@router.post('/seasons/{season_id}/clans/{clan_id}/market')
def market(season_id: int, clan_id: int, payload: MarketInput,
           db: Session = Depends(get_db), user: User = Depends(get_onboarded_active_user)):
    return _mutate(db, season_id, clan_id, user.id, payload.expected_revision, lambda state, now: store.market(
        db, state_id=state.id, actor_id=user.id, resource=payload.resource,
        quantity=payload.quantity, buying=payload.buying, expected_revision=state.revision))
