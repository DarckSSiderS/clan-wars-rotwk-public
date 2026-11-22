"""One-shot campaign fixtures for an explicitly isolated preview.db, never a deployment.

Usage: python scripts/seed_campaign_preview.py --database .tmp/<copy>/preview.db --worker-disabled
No app startup, migration, worker, network, credentials or session creation occurs here.
"""

import argparse
from datetime import datetime, timedelta, timezone
from itertools import combinations
import json
import os
from pathlib import Path
import sqlite3
import sys
from uuid import NAMESPACE_URL, uuid4, uuid5


ROOT = Path(__file__).resolve().parents[1]
SERVER_DATABASE = '/home/clanwar/apps/clanwar-preview/shared/preview.db'
SEED_KEY = 'demo:preview-campaign:v1'
REVIEW_UUID = str(uuid5(NAMESPACE_URL, 'local-replay-acceptance:1'))


def validate_database_path(database, *, allow_server_preview=False):
    raw = Path(database)
    if '..' in raw.parts:
        raise ValueError('Parent traversal is not allowed')
    server = allow_server_preview and os.name == 'posix' and str(raw) == SERVER_DATABASE
    if allow_server_preview and not server:
        raise ValueError('Server opt-in accepts only the exact preview database path')
    absolute = raw.absolute()
    tmp = ROOT / '.tmp'
    local = absolute.is_relative_to(tmp) and len(absolute.relative_to(tmp).parts) >= 2
    if absolute.name != 'preview.db' or not (server or local):
        raise ValueError('Only .tmp/<directory>/preview.db or the opted-in server preview.db is allowed')
    for part in (absolute, *absolute.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise ValueError('Database paths must not contain links or junctions')
    try:
        path = absolute.resolve(strict=True)
    except OSError as error:
        raise ValueError('An existing preview.db is required') from error
    local = path.is_relative_to(tmp) and len(path.relative_to(tmp).parts) >= 2
    if path.name != 'preview.db' or not (server or local) or not path.is_file():
        raise ValueError('Only .tmp/<directory>/preview.db or the opted-in server preview.db is allowed')
    if path.stat().st_nlink != 1:
        raise ValueError('Hardlinked databases are forbidden')
    return path


def _select_lands(lands):
    available = {t.id: t for t in lands if t.owner_clan_id is None
                 and not t.has_port and not t.is_great_stronghold}
    neighbours = {i: set(t.adjacent_territory_ids or []) & available.keys()
                  for i, t in available.items()}
    triples = set()
    for centre, near in neighbours.items():
        for left, right in combinations(sorted(near), 2):
            triples.add(tuple(sorted((centre, left, right))))
    for target in sorted(available):
        candidates = [t for t in sorted(triples) if target not in t
                      and any(target in neighbours[i] for i in t)]
        for first in candidates:
            for second in candidates:
                if set(first) & set(second):
                    continue
                for third in candidates:
                    used = set(first + second + third) | {target}
                    if len(used) != 10:
                        continue
                    spare = sorted((set(available) - used) & set().union(*(neighbours[i] for i in first)))
                    if spare:
                        return [list(first), list(second), list(third)], [target, spare[0]]
    raise ValueError('Need three disjoint connected ordinary triples and two available battle lands')


def _preflight(db):
    from sqlalchemy import inspect, select
    from app.core.clan_colors import CLAN_MAP_COLORS
    from app.core.time import as_utc
    from app.database import Base
    from app.models.campaign import CampaignSeason, CampaignRuleSet
    from app.models.campaign_cycle import CampaignCycleRecord
    from app.models.clan import Clan
    from app.models.cycle_market import CycleMarketCommand
    from app.models.cycle_income import CycleTerritoryProfile
    from app.models.external_identity import ExternalPlayerIdentity
    from app.models.territory import Territory, TerritoryOwnershipHistory
    from app.models.user import User
    from app.models.role import Role
    from app.models.worker import WorkerHeartbeat

    inspector = inspect(db.bind)
    tables = set(inspector.get_table_names())
    needed = ('users', 'roles', 'clans', 'clan_members', 'clan_membership_periods',
              'external_player_identities', 'territories', 'territory_ownership_history',
              'campaign_seasons', 'campaign_rule_sets', 'campaign_cycles',
              'campaign_cycle_plans', 'campaign_cycle_plan_revisions', 'cycle_economy_states',
              'cycle_diplomacy_pairs', 'cycle_territory_battles', 'cycle_score_adjustments',
              'cycle_market_offers', 'cycle_market_caravans', 'cycle_market_commands', 'worker_heartbeats')
    for name in needed:
        if name not in tables or not set(Base.metadata.tables[name].columns.keys()) <= {
                c['name'] for c in inspector.get_columns(name)}:
            raise ValueError('Missing cycle_v1 schema: ' + name)
    if any(row.heartbeat_at and as_utc(row.heartbeat_at) >= datetime.now(timezone.utc)-timedelta(minutes=10)
           for row in db.query(WorkerHeartbeat)):
        raise ValueError('Recent worker heartbeat: disable the preview worker and wait ten minutes')
    if db.query(CycleMarketCommand).filter_by(command_id=SEED_KEY).first() or db.query(Clan).filter(
            Clan.name.like('DEMO Preview %')).first():
        raise ValueError('Preview campaign seed already exists; restore the backup or use a fresh copy')
    review = db.query(User).filter_by(username='local-review').one_or_none()
    if (review is None or not review.is_active or not review.is_claimed
            or not review.role or review.role.name != 'admin'
            or review.display_name != 'local-review' or review.email or review.hashed_password
            or review.onboarding_completed_at is None):
        raise ValueError('An existing onboarded synthetic local-review admin without credentials is required')
    identities = db.query(ExternalPlayerIdentity).filter_by(user_id=review.id).all()
    if (len(identities) != 1 or identities[0].source != 'bfmeladder'
            or identities[0].external_uuid != REVIEW_UUID
            or identities[0].current_nickname != 'local-review'
            or identities[0].verification_status != 'verified'):
        raise ValueError('local-review must have the exact synthetic rehearsal identity')
    season = db.query(CampaignSeason).filter_by(status='active').one_or_none()
    if season is None or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
        raise ValueError('An existing active cycle_v1 season is required; no implicit reset or migration')
    rule = db.query(CampaignRuleSet).filter_by(is_active=True).one_or_none()
    if rule is None:
        raise ValueError('An existing active campaign rule set is required')
    empty_cycles = db.query(CampaignCycleRecord).filter_by(season_id=season.id, settled_at=None).all()
    for cycle in empty_cycles:
        if (cycle.battles_registered or cycle.orders_frozen_at or cycle.import_verified_at
                or cycle.dependencies
                or as_utc(cycle.preparation_at) > datetime.now(timezone.utc)):
            raise ValueError('Only empty past preview cycles may be archived before seeding')
        for table in Base.metadata.sorted_tables:
            # Diplomacy is season-wide; retain its append-only journal unchanged.
            if table.name == 'cycle_diplomacy_events':
                continue
            for column in table.columns:
                if any(fk.target_fullname == 'campaign_cycles.id' for fk in column.foreign_keys):
                    if db.execute(select(column).where(column == cycle.id).limit(1)).first():
                        raise ValueError('An unfinished preview cycle contains dependent records')
    ordinary = db.query(Role).filter_by(name='user').one_or_none()
    if ordinary is None:
        raise ValueError('An existing ordinary user role is required')
    occupied = {color.upper() for (color,) in db.query(Clan.map_color) if color}
    available_colors = CLAN_MAP_COLORS - occupied
    preferences = ['#00ACC1', '#FFB300', '#D81B60']
    colors = [c for c in preferences if c in available_colors]
    colors += sorted(available_colors - set(colors))
    if len(colors) < 3:
        raise ValueError('Three unused map colors are required')
    lands = db.query(Territory).filter_by(is_playable=True).order_by(Territory.id).all()
    groups, battle_lands = _select_lands(lands)
    selected = [i for group in groups for i in group] + battle_lands
    configured = {row.territory_id for row in db.query(CycleTerritoryProfile).filter_by(season_id=season.id)}
    if not set(selected) <= configured:
        raise ValueError('Selected preview lands require existing configured income profiles')
    if db.query(TerritoryOwnershipHistory).filter(
            TerritoryOwnershipHistory.territory_id.in_(selected),
            TerritoryOwnershipHistory.ended_at.is_(None)).first():
        raise ValueError('Available lands have conflicting open ownership history')
    for n in range(1, 18):
        name = f'demo-preview-player-{n:02}'
        identity = str(uuid5(NAMESPACE_URL, SEED_KEY + ':' + name))
        if db.query(User.id).filter_by(username=name).first() or db.query(ExternalPlayerIdentity.id).filter_by(
                source='bfmeladder', external_uuid=identity).first():
            raise ValueError('Synthetic player name/UUID collision')
    return review, season, rule, groups, battle_lands, ordinary.id, colors[:3], empty_cycles


def _backup(path, *, label='campaign-seed'):
    backup = path.with_name('preview.before-' + label + '.' + uuid4().hex + '.db.bak')
    fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as source:
        with sqlite3.connect(backup) as target:
            source.backup(target)
            if target.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise ValueError('Backup integrity check failed')
    return backup


def _populate(db, *, now, context):
    from sqlalchemy import func
    from app.models.campaign_cycle import CampaignCycleRecord, CampaignCyclePlan
    from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
    from app.models.cycle_battle import CycleTerritoryBattle
    from app.models.cycle_diplomacy import CycleDiplomacyPair
    from app.models.cycle_market import CycleMarketCaravan
    from app.models.cycle_income import CycleIncomeAccrual
    from app.models.external_identity import ExternalPlayerIdentity
    from app.models.territory import Territory, TerritoryOwnershipHistory
    from app.models.user import User
    from app.services.campaign_cycle_store import CampaignCycleStore
    from app.services.cycle_battle_service import CycleBattleService
    from app.services.cycle_economy import Resources
    from app.services.cycle_economy_store import CycleEconomyStore
    from app.services.cycle_market_service import CycleMarketService
    from app.services.cycle_orders import Order
    from app.services.cycle_plan_service import CyclePlanService

    review, season, rule, groups, targets, ordinary_role_id, colors, empty_cycles = context
    for empty in empty_cycles:
        shift = max(timedelta(), CampaignCycleStore.timeline(empty).replay_deadline - now)
        empty.starts_at -= shift
        empty.preparation_at -= shift
        empty.settled_at = now
    history_start = now - timedelta(hours=85)
    players = [review]
    for n in range(1, 18):
        name = f'demo-preview-player-{n:02}'
        user = User(username=name, display_name='DEMO Player ' + str(n), role_id=ordinary_role_id,
                    hashed_password=None, email=None, is_active=True, is_claimed=False,
                    created_at=history_start, onboarding_completed_at=now)
        db.add(user)
        db.flush()
        db.add(ExternalPlayerIdentity(user_id=user.id, source='bfmeladder',
            external_uuid=str(uuid5(NAMESPACE_URL, SEED_KEY + ':' + name)), current_nickname=name,
            verification_status='verified', first_seen_at=history_start, last_seen_at=history_start,
            verified_at=history_start))
        players.append(user)
    rosters = [players[i:i+6] for i in (0, 6, 12)]
    clans = [Clan(name='DEMO Preview ' + name, description='Synthetic isolated preview campaign; not real players.',
                  leader_id=roster[0].id, level=3, territory_points=400, created_at=history_start,
                  is_admin_clan=False, is_recruiting=False, map_color=color)
             for name, roster, color in zip(('Review', 'Allies', 'Neutral'), rosters, colors)]
    db.add_all(clans)
    db.flush()
    # Move only this known synthetic membership; preserve all previous clan/user/history rows.
    for member in db.query(ClanMember).filter_by(user_id=review.id).all():
        period = db.query(ClanMembershipPeriod).filter_by(user_id=review.id, ended_at=None).one_or_none()
        if period is None:
            db.add(ClanMembershipPeriod(user_id=review.id, clan_id=member.clan_id,
                started_at=member.joined_at, ended_at=now, started_reason='joined', ended_reason='preview_seed'))
        else:
            period.ended_at, period.ended_reason = now, 'preview_seed'
        db.delete(member)
    db.flush()
    for clan, roster, group in zip(clans, rosters, groups):
        for user in roster:
            joined = now if user.id == review.id else history_start
            db.add(ClanMember(clan_id=clan.id, user_id=user.id, joined_at=joined))
            db.add(ClanMembershipPeriod(clan_id=clan.id, user_id=user.id, started_at=joined,
                                       started_reason='preview_seed'))
        for tid in group:
            land = db.get(Territory, tid)
            land.owner_clan_id, land.owned_since = clan.id, now
            db.add(TerritoryOwnershipHistory(territory_id=tid, clan_id=clan.id,
                                           started_at=now, reason='preview_seed'))
    db.flush()
    economy = CycleEconomyStore()
    wallets = []
    for clan in clans:
        wallet = economy.ensure_state(db, season_id=season.id, clan_id=clan.id)
        economy._write(db, wallet, wallet=economy._wallet(Resources(100000, 1000, 1000, 1000, 100)))
        # The demo grant starts now; it must not replay income from older cycles.
        db.add(CycleIncomeAccrual(state_id=wallet.id, accrued_through=now, residuals={}))
        wallets.append(wallet)
    db.add(CycleDiplomacyPair(season_id=season.id, clan_low_id=min(clans[0].id, clans[1].id),
        clan_high_id=max(clans[0].id, clans[1].id), allied_at=now, declarations={}))
    number = (db.query(func.max(CampaignCycleRecord.number)).filter_by(season_id=season.id).scalar() or 0) + 1
    # An explicitly synthetic historical fixture, not a forged Arena replay or an old-cycle rewrite.
    history = CampaignCycleRecord(season_id=season.id, number=number, rule_version=rule.version,
        starts_at=history_start, preparation_at=history_start, orders_frozen_at=history_start+timedelta(hours=24),
        import_verified_at=now-timedelta(hours=12, minutes=1), settled_at=now-timedelta(hours=12, minutes=1),
        battles_registered=True, dependencies={'demo:synthetic-history': True}, planning_snapshot=[])
    db.add(history)
    db.flush()
    battle = CycleTerritoryBattle(cycle_id=history.id, territory_id=targets[1],
        sides=[{'clan_id': clans[i].id, 'user_ids': [rosters[i][1].id]} for i in (0, 2)],
        completed_at=history.settled_at, winner_clan_id=clans[0].id,
        recalculated_winner_clan_id=clans[0].id)
    db.add(battle)
    db.flush()
    for i, score in ((0, 120), (2, -40)):
        CycleBattleService().adjust(db, battle_id=battle.id, clan_id=clans[i].id, amount=score,
            command_id=SEED_KEY + f':history:{i}', actor_user_id=review.id,
            reason='DEMO synthetic preview score; no Arena replay or ownership transfer')
    history.planning_snapshot = [dict(id=t.id, owner_clan_id=t.owner_clan_id,
        neighbours=list(t.adjacent_territory_ids or []), coastal=bool(t.is_coastal),
        port=bool(t.has_port), fortress=t.is_great_stronghold)
        for t in db.query(Territory).filter_by(is_playable=True).order_by(Territory.id)]
    db.flush()
    cycle = CampaignCycleStore().advance(db, cycle_id=history.id, now=now-timedelta(minutes=1), rule_version=rule.version)
    CyclePlanService().capture_preparation(db, cycle_id=cycle.id, now=now)
    for i, (clan, roster, group) in enumerate(zip(clans, rosters, groups)):
        source = next(tid for tid in group if targets[0] in (db.get(Territory, tid).adjacent_territory_ids or []))
        orders = ([Order(roster[j].id, 'attack', targets[0], source) for j in range(2)] if i != 1 else
                  [Order(roster[j].id, 'defend', group[0]) for j in range(2)])
        orders += [Order(roster[2].id, 'defend', group[1]),
                   Order(roster[4].id, 'reserve'), Order(roster[5].id, 'reserve')]
        CyclePlanService().save(db, cycle_id=cycle.id, clan_id=clan.id, actor_user_id=roster[0].id,
                                expected_revision=0, orders=orders, now=now)
    market = CycleMarketService()

    def offer(sender, target, suffix, offered, requested):
        return market.create(db, cycle_id=cycle.id, clan_id=clans[sender].id,
            actor_id=rosters[sender][0].id, target_clan_id=clans[target].id,
            offered=offered, requested=requested, now=now, command_id=SEED_KEY+suffix,
            expected_wallet_revision=wallets[sender].revision)

    transit = offer(1, 0, ':transit', {'food': 10}, {'mithril': 1})
    market.accept(db, cycle_id=cycle.id, offer_id=transit.id, clan_id=clans[0].id,
        actor_id=review.id, now=now, command_id=SEED_KEY+':accept-transit', expected_revision=transit.revision,
        expected_sender_revision=wallets[1].revision, expected_wallet_revision=wallets[0].revision)
    outgoing = offer(0, 2, ':outgoing', {'iron': 20}, {'wood': 15})
    incoming = offer(2, 0, ':incoming', {'wood': 25}, {'iron': 10})
    quote = market.quote(db, cycle_id=cycle.id, offer_id=incoming.id, clan_id=clans[0].id,
                         actor_id=review.id, now=now)
    outgoing_quote = market.quote(db, cycle_id=cycle.id, offer_id=outgoing.id, clan_id=clans[2].id,
                                  actor_id=rosters[2][0].id, now=now)
    from app.services.cycle_preparation_service import CyclePreparationService
    from app.services.cycle_reinforcement_store import CycleReinforcementStore
    preparation = CyclePreparationService().read(db, cycle_id=cycle.id, clan_id=clans[0].id,
                                                actor_id=review.id, now=now)
    planning = CyclePlanService().planning(db, cycle_id=cycle.id, clan_id=clans[0].id,
                                          actor_user_id=review.id, now=now)
    help_context = CycleReinforcementStore().context(db, cycle_id=cycle.id, viewer_clan_id=clans[0].id,
                                                    actor_user_id=review.id, now=now)
    readiness = dict(can_request_scout=preparation['scout']['can_request'],
                     planning_editable=planning['editable'], trade_quote_available=bool(quote),
                     reinforcements_can_command=help_context['can_command'])
    if not readiness['can_request_scout'] or not readiness['planning_editable']:
        raise ValueError('Seed did not produce actionable preparation/scouting; rolling back')
    timeline = CampaignCycleStore.timeline(cycle)
    return dict(seed=SEED_KEY, season_id=season.id, cycle_id=cycle.id, cycle_number=cycle.number,
        phase=timeline.phase_at(now).value, preparation_at=timeline.preparation_at.isoformat(),
        battle_at=timeline.battle_at.isoformat(), scout_cutoff=(timeline.battle_at-timedelta(hours=6)).isoformat(),
        history_cycle_id=history.id, history_battle_id=battle.id, review_user_id=review.id,
        readiness=readiness, ownership={str(t): c.id for c, group in zip(clans, groups) for t in group},
        clans=[dict(id=c.id, name=c.name, map_color=c.map_color, leader_user_id=r[0].id, territory_ids=g,
                    member_user_ids=[u.id for u in r], reserve_user_ids=[u.id for u in r[4:]],
                    wallet=dict(w.wallet), wallet_revision=w.revision)
               for c, r, g, w in zip(clans, rosters, groups, wallets)],
        battle_territory_ids=targets, incoming_offer_id=incoming.id, outgoing_offer_id=outgoing.id,
        transit_offer_id=transit.id,
        caravan_ids=[c.id for c in db.query(CycleMarketCaravan).filter_by(offer_id=transit.id)],
        incoming_quote={k: str(v) if isinstance(v, datetime) else v for k, v in quote.items()},
        outgoing_quote={k: str(v) if isinstance(v, datetime) else v for k, v in outgoing_quote.items()},
        worker_started=False,
        limitations=['Worker must remain disabled; no automatic reveal, delivery or income.',
                    'Help opens only after an explicit normal reveal at battle_at.',
                    'Only empty unfinished preview cycles are archived; existing battle history is preserved.',
                    'Old synthetic leader pointers are preserved; only local-review membership moves.'])


def seed_preview(database, *, worker_disabled=False, allow_server_preview=False):
    if not worker_disabled:
        raise ValueError('Confirm the preview worker is disabled with --worker-disabled')
    path = validate_database_path(database, allow_server_preview=allow_server_preview)
    # Configure before any domain import. Importing app.main/worker is intentionally forbidden.
    if 'app.database' not in sys.modules:
        os.environ.update(DATABASE_URL='sqlite:///' + path.as_posix(), ENVIRONMENT='test',
                          DISCORD_ENABLED='false', REDIS_URL='', BFME_OAUTH_ENABLED='false',
                          BOOTSTRAP_TEST_ADMIN_ENABLED='false')
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    import app.models  # noqa: F401
    from app.models.cycle_market import CycleMarketCommand

    engine = create_engine('sqlite:///' + path.as_posix())
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            connection.commit()
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            try:
                with Session(bind=connection) as db:
                    context = _preflight(db)
                    if connection.exec_driver_sql('PRAGMA quick_check').scalar() != 'ok':
                        raise ValueError('Database integrity check failed')
                    backup = _backup(path)
                    report = _populate(db, now=datetime.now(timezone.utc), context=context)
                    report.update(database=str(path), backup=str(backup))
                    db.add(CycleMarketCommand(season_id=context[1].id, command_id=SEED_KEY,
                        payload={'kind': 'synthetic-preview-seed'}, result=report))
                    db.flush()
                    if connection.exec_driver_sql('PRAGMA foreign_key_check').first():
                        raise ValueError('Foreign-key check failed; seed rolled back')
                connection.commit()
                return report
            except Exception:
                connection.rollback()
                raise
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--worker-disabled', action='store_true', help='Operator confirms no worker writes this preview DB')
    parser.add_argument('--allow-server-preview', action='store_true', help='Allow only the exact server preview path')
    args = parser.parse_args()
    try:
        report = seed_preview(args.database, worker_disabled=args.worker_disabled,
                              allow_server_preview=args.allow_server_preview)
    except (ValueError, OSError) as error:
        parser.exit(2, f'Preview seed refused: {error}\n')
    print(json.dumps(report, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
