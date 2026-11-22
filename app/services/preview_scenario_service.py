"""Private preview controls. Never imported or routed by the production app.

Only a seeded, strictly allowlisted preview.db is opened. Caller supplies no ORM
session: this module owns one checked SQLite transaction, with a backup before
each actual change. No worker, settlement, income, replay fetch or session issue.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3


@contextmanager
def _database(database, *, write=False):
    from scripts.seed_campaign_preview import SERVER_DATABASE, validate_database_path

    path = validate_database_path(database, allow_server_preview=(
        os.name == 'posix' and str(database) == SERVER_DATABASE))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.exc import SQLAlchemyError
    import app.models  # noqa: F401

    mode = 'rw' if write else 'ro'
    engine = create_engine('sqlite://', creator=lambda: sqlite3.connect(
        path.as_uri() + '?mode=' + mode, uri=True, check_same_thread=False))
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            connection.commit()
            if write:
                connection.exec_driver_sql('BEGIN IMMEDIATE')
            try:
                with Session(bind=connection) as db:
                    yield path, db, connection
            except SQLAlchemyError as error:
                raise ValueError('Invalid preview schema or conflicting scenario data') from error
            finally:
                connection.rollback()
    finally:
        engine.dispose()


def _context(db):
    from scripts.seed_campaign_preview import SEED_KEY, REVIEW_UUID
    from app.core.time import as_utc
    from app.models.campaign import CampaignSeason
    from app.models.campaign_cycle import CampaignCycleRecord, CampaignCyclePlan
    from app.models.clan import Clan, ClanMember
    from app.models.cycle_market import CycleMarketCommand
    from app.models.cycle_startup import CycleStartup
    from app.models.external_identity import ExternalPlayerIdentity
    from app.models.territory import Territory
    from app.models.user import User
    from app.models.worker import WorkerHeartbeat

    marker = db.query(CycleMarketCommand).filter_by(command_id=SEED_KEY).one_or_none()
    if marker is None or marker.payload != {'kind': 'synthetic-preview-seed'}:
        raise ValueError('Preview campaign seed is required')
    report = marker.result
    if not isinstance(report, dict) or report.get('seed') != SEED_KEY or len(report.get('clans', [])) != 3:
        raise ValueError('Invalid preview seed manifest')
    review = db.get(User, report.get('review_user_id'))
    identity = db.query(ExternalPlayerIdentity).filter_by(user_id=report.get('review_user_id')).all()
    if (review is None or review.username != 'local-review' or review.display_name != 'local-review'
            or not review.is_active or not review.is_claimed or not review.onboarding_completed_at
            or not review.role or review.role.name != 'admin' or review.hashed_password or review.email
            or len(identity) != 1 or identity[0].source != 'bfmeladder'
            or identity[0].external_uuid != REVIEW_UUID or identity[0].current_nickname != 'local-review'
            or identity[0].verification_status != 'verified'):
        raise ValueError('Verified synthetic local-review admin required')
    if any(w.heartbeat_at and as_utc(w.heartbeat_at) >= datetime.now(timezone.utc)-timedelta(minutes=10)
           for w in db.query(WorkerHeartbeat)):
        raise ValueError('Disable the preview worker and wait ten minutes')
    cycle = db.get(CampaignCycleRecord, report.get('cycle_id'))
    season = db.get(CampaignSeason, marker.season_id)
    if (cycle is None or season is None or cycle.season_id != season.id
            or report.get('season_id') != season.id or season.status != 'active'
            or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1'
            or cycle.settled_at is not None or cycle.import_verified_at is not None
            or db.query(CampaignCycleRecord.id).filter(CampaignCycleRecord.season_id == season.id,
                                                       CampaignCycleRecord.number > cycle.number).first()):
        raise ValueError('Unsettled latest seeded demo cycle in an active cycle_v1 season required')
    if db.query(CycleStartup).filter_by(cycle_id=cycle.id).first():
        raise ValueError('A runtime-managed startup cycle cannot be switched')
    ids = set()
    for clan_data, expected_name in zip(report['clans'], ('Review', 'Allies', 'Neutral')):
        clan = db.get(Clan, clan_data['id'])
        if (clan is None or clan.name != 'DEMO Preview ' + expected_name or clan.is_deleted
                or clan.is_admin_clan or clan.leader_id != clan_data['leader_user_id']):
            raise ValueError('Original sandbox-only DEMO clans required')
        members = db.query(ClanMember.user_id).filter_by(clan_id=clan.id).all()
        if {uid for (uid,) in members} != set(clan_data['member_user_ids']):
            raise ValueError('Demo roster changed; refusing to reset foreign players')
        ids.add(clan.id)
    membership = db.query(ClanMember).filter_by(user_id=review.id).all()
    if (len(membership) != 1 or membership[0].clan_id != report['clans'][0]['id']
            or report['clans'][0]['leader_user_id'] != review.id):
        raise ValueError('local-review must lead the seeded demo clan')
    for tid, owner in report['ownership'].items():
        land = db.get(Territory, int(tid))
        if land is None or land.owner_clan_id != owner:
            raise ValueError('Demo ownership changed; no ownership rollback is permitted')
    for plan in db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id):
        if plan.clan_id not in ids and plan.orders:
            raise ValueError('Foreign clan orders cannot be revealed or reset')
        roster = next((set(c['member_user_ids']) for c in report['clans'] if c['id'] == plan.clan_id), set())
        for order in plan.orders:
            if order['user_id'] not in roster:
                raise ValueError('Foreign player orders cannot be revealed or reset')
    return marker, report, cycle


def _reveal_blocker(db, cycle_id):
    from app.models.campaign_cycle import CampaignCyclePlan
    from app.models.territory import Territory

    for plan in db.query(CampaignCyclePlan).filter_by(cycle_id=cycle_id):
        for order in plan.orders:
            if order['kind'] == 'attack':
                land = db.get(Territory, order['territory_id'])
                if land is None or land.owner_clan_id is not None:
                    return 'Preview reveal only supports attacks on unowned lands; no wars/refunds'
    return None


def _view(db, context, now):
    from app.models.campaign_cycle import CycleScoutRequest
    from app.services.campaign_cycle_store import CampaignCycleStore
    from app.services.cycle_market_service import CycleMarketService
    from app.services.cycle_plan_service import CyclePlanService
    from app.services.cycle_preparation_service import CyclePreparationService
    from app.services.cycle_reinforcement_store import CycleReinforcementStore

    _, report, cycle = context
    clan = report['clans'][0]
    actor = report['review_user_id']
    timeline = CampaignCycleStore.timeline(cycle)
    planning = CyclePlanService().planning(db, cycle_id=cycle.id, clan_id=clan['id'], actor_user_id=actor, now=now)
    helps = CycleReinforcementStore().context(db, cycle_id=cycle.id, viewer_clan_id=clan['id'], actor_user_id=actor, now=now)
    can_scout = False
    if planning['phase'] == 'preparation' and now < timeline.battle_at-timedelta(hours=6):
        can_scout = CyclePreparationService().read(db, cycle_id=cycle.id, clan_id=clan['id'],
                                                  actor_id=actor, now=now)['scout']['can_request']
    from app.models.cycle_market import CycleMarketOffer
    incoming = db.get(CycleMarketOffer, report['incoming_offer_id'])
    quote = None
    trade_error = None
    if incoming and incoming.status == 'pending':
        try:
            quote = CycleMarketService().quote(db, cycle_id=cycle.id, offer_id=incoming.id,
                                               clan_id=clan['id'], actor_id=actor, now=now)
            quote = {k: v.isoformat() if isinstance(v, datetime) else v for k, v in quote.items()}
        except (ValueError, PermissionError) as error:
            trade_error = str(error)
    scout = db.query(CycleScoutRequest).filter_by(cycle_id=cycle.id, clan_id=clan['id']).one_or_none()
    blocker = _reveal_blocker(db, cycle.id) if cycle.orders_frozen_at is None else None
    return dict(mode='battle' if cycle.orders_frozen_at is not None else 'preparation',
        cycle_id=cycle.id, season_id=cycle.season_id, phase=planning['phase'], server_time=now.isoformat(),
        preparation_at=timeline.preparation_at.isoformat(), battle_at=timeline.battle_at.isoformat(),
        scout_cutoff=(timeline.battle_at-timedelta(hours=6)).isoformat(),
        command_deadline=(timeline.battle_at+timedelta(hours=24)).isoformat(),
        can_request_scout=can_scout, planning_editable=planning['editable'],
        scout_report=scout.report if scout else None, trade_quote=quote, quote_available=quote is not None, trade_disabled_reason=trade_error,
        can_switch_to_battle=blocker is None, disableReason=blocker,
        reinforcements_can_command=helps['can_command'], reinforcements_ready=helps['ready'],
        available_reserve_user_ids=[p['user_id'] for p in helps['players'] if p['available']],
        own_targets=helps['own_targets'], allied_targets=helps['allied_targets'],
        reinforcement_revision=helps['state']['revision'] if helps['state'] else None,
        reset_confirmation_required=cycle.orders_frozen_at is not None,
        reset_count=report.get('scenario', {}).get('reset_count', 0))


def read_preview_scenario(database: Path) -> dict:
    """Read-only, no session touch/commit; ValueError when not a seeded preview."""
    with _database(database) as (_, db, _):
        return _view(db, _context(db), datetime.now(timezone.utc))


def _reveal(db, context, now):
    from app.core.time import as_utc
    from app.models.campaign_cycle import CampaignCyclePlan, CampaignCyclePlanRevision, CycleScoutRequest
    from app.services.campaign_cycle_store import CampaignCycleStore
    from app.services.cycle_reconnaissance_service import CycleReconnaissanceService
    from app.services.cycle_reinforcement_store import CycleReinforcementStore
    from app.services.cycle_reveal_service import CycleRevealService

    _, report, cycle = context
    blocker = _reveal_blocker(db, cycle.id)
    if blocker:
        raise ValueError(blocker)
    # Retime the entire preparation together, preserving paid scouting's cutoff semantics.
    preparation = now-timedelta(hours=24)
    delta = preparation-as_utc(cycle.preparation_at)
    plans = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id).all()
    plan_ids = [p.id for p in plans]
    for revision in db.query(CampaignCyclePlanRevision).filter(CampaignCyclePlanRevision.plan_id.in_(plan_ids)):
        revision.saved_at = as_utc(revision.saved_at)+delta
    scouts = db.query(CycleScoutRequest).filter_by(cycle_id=cycle.id).all()
    for scout in scouts:
        scout.requested_at = as_utc(scout.requested_at)+delta
    cycle.starts_at = cycle.preparation_at = preparation
    CampaignCycleStore._bump(db, cycle)
    db.flush()
    CycleRevealService().reveal(db, cycle_id=cycle.id, now=now)
    for scout in scouts:
        actor = next(c['leader_user_id'] for c in report['clans'] if c['id'] == scout.clan_id)
        CycleReconnaissanceService().report(db, request_id=scout.id, actor_user_id=actor, now=now)
    # Materialize one normal allied help request so the single preview admin can send help.
    ally = report['clans'][1]
    store = CycleReinforcementStore()
    ally_context = store.context(db, cycle_id=cycle.id, viewer_clan_id=ally['id'],
                                 actor_user_id=ally['leader_user_id'], now=now)
    if ally_context['help_targets']:
        store.request_help(db, cycle_id=cycle.id, clan_id=ally['id'],
            actor_user_id=ally['leader_user_id'], territory_id=ally_context['help_targets'][0],
            request_id='demo:preview-allied-help', expected_revision=ally_context['state']['revision'], now=now)


def _reset(db, context, now):
    from app.models.campaign_cycle import CampaignCyclePlan, CycleScoutRequest
    from app.models.cycle_battle import (CycleTerritoryBattle, CycleMatchContribution, CycleScoreAdjustment,
                                       CycleLateReplayDecision, CycleOwnershipCorrection)
    from app.models.cycle_diplomacy import CycleDiplomacyEvent
    from app.models.cycle_dispatch_route import CycleDispatchRoute
    from app.models.cycle_economy import CycleEconomySnapshot
    from app.models.cycle_interception import CycleInterception
    from app.models.cycle_reinforcement_state import CycleReinforcementState
    from app.services.campaign_cycle_store import CampaignCycleStore
    from app.services.cycle_orders import Order
    from app.services.cycle_plan_service import CyclePlanService

    _, report, cycle = context
    battle_ids = [b.id for b in db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle.id)]
    for model in (CycleMatchContribution, CycleScoreAdjustment, CycleLateReplayDecision, CycleOwnershipCorrection):
        if db.query(model).filter(model.battle_id.in_(battle_ids)).first():
            raise ValueError('Demo has accounted battle evidence; restore a preview backup instead of erasing it')
    if (db.query(CycleInterception).filter_by(cycle_id=cycle.id).first()
            or db.query(CycleDiplomacyEvent).filter_by(cycle_id=cycle.id).first()
            or db.query(CycleOwnershipCorrection).filter_by(current_cycle_id=cycle.id).first()):
        raise ValueError('Accounted demo events require a backup restore, not scenario reset')
    # Only children of this exact, manifest-marked demo cycle may be cleared.
    for model in (CycleDispatchRoute, CycleReinforcementState, CycleEconomySnapshot,
                  CycleScoutRequest, CycleTerritoryBattle):
        db.query(model).filter_by(cycle_id=cycle.id).delete(synchronize_session=False)
    rosters = {c['id']: c for c in report['clans']}
    plans = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id).all()
    drafts = []
    for plan in plans:
        if plan.clan_id in rosters:
            drafts.append((plan.clan_id, list(plan.orders), plan.revision))
            plan.frozen_at, plan.snapshot = None, None
        else:
            # Reveal's empty placeholders are scoped to the demo cycle, not old plans.
            if plan.orders:
                raise ValueError('Cannot reset a foreign clan plan')
            db.delete(plan)
    cycle.starts_at = cycle.preparation_at = now
    cycle.orders_frozen_at, cycle.planning_snapshot = None, None
    cycle.battles_registered, cycle.season_end_requested, cycle.dependencies = False, False, {}
    CampaignCycleStore._bump(db, cycle)
    db.flush()
    service = CyclePlanService()
    service.capture_preparation(db, cycle_id=cycle.id, now=now)
    for clan_id, orders, revision in drafts:
        service.save(db, cycle_id=cycle.id, clan_id=clan_id, actor_user_id=rosters[clan_id]['leader_user_id'],
                     expected_revision=revision, orders=[Order(**o) for o in orders], now=now)


def switch_preview_scenario(database: Path, mode: str, *, confirm_reset: bool = False) -> dict:
    """Switch the marked latest demo cycle; preparation reset requires explicit confirmation.

    Same-mode requests are no-ops, including confirm_reset=True. Reset retains
    plans, wallets, market escrow/transit and all original history. It clears only
    demo-cycle battles/dispatches/scouting/snapshots; paid scouting is not refunded.
    """
    if mode not in ('preparation', 'battle') or type(confirm_reset) is not bool:
        raise ValueError('mode must be preparation or battle; confirm_reset must be boolean')
    from scripts.seed_campaign_preview import _backup

    with _database(database, write=True) as (path, db, connection):
        context = _context(db)
        marker, report, cycle = context
        current = 'battle' if cycle.orders_frozen_at is not None else 'preparation'
        now = datetime.now(timezone.utc)
        if mode == current:
            return _view(db, context, now)
        if mode == 'preparation' and not confirm_reset:
            raise ValueError('Returning to preparation clears demo battles; confirm_reset=True is required')
        if mode == 'battle' and (blocker := _reveal_blocker(db, cycle.id)):
            raise ValueError(blocker)
        backup = _backup(path, label='preview-scenario')
        if mode == 'battle':
            _reveal(db, context, now)
        else:
            _reset(db, context, now)
        state = dict(report.get('scenario', {}))
        state.update(mode=mode, changed_at=now.isoformat(), backup=str(backup),
                     reset_count=state.get('reset_count', 0)+(mode == 'preparation'))
        marker.result = {**report, 'scenario': state}
        db.flush()
        context = marker, marker.result, cycle
        result = _view(db, context, now)
        result['backup'] = str(backup)
        if connection.exec_driver_sql('PRAGMA foreign_key_check').first():
            raise ValueError('Foreign-key check failed; preview switch rolled back')
        connection.commit()
        return result
