"""Preview-only seed safety and real authenticated campaign commands."""

import hashlib
import importlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.campaign import CampaignRuleSet, CampaignSeason
from app.models.clan import Clan, ClanMember
from app.models.cycle_income import CycleTerritoryProfile
from app.models.external_identity import ExternalPlayerIdentity
from app.models.role import Role
from app.models.territory import Territory
from app.models.user import User
from app.core.campaign_rules import default_campaign_rule_values


ROOT = Path(__file__).resolve().parents[1]


def seeder():
    assert (ROOT / 'scripts/seed_campaign_preview.py').is_file(), 'Preview campaign seed is missing'
    return importlib.import_module('scripts.seed_campaign_preview')


def scenarios():
    assert (ROOT / 'app/services/preview_scenario_service.py').is_file(), 'Preview scenario helper is missing'
    return importlib.import_module('app.services.preview_scenario_service')


@pytest.fixture
def preview():
    folder = ROOT / '.tmp' / ('preview-seed-test-' + uuid4().hex)
    folder.mkdir(parents=True)
    path = folder / 'preview.db'
    engine = create_engine('sqlite:///' + path.as_posix())
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add_all([Role(id=1, name='admin'), Role(id=2, name='user')])
        db.flush()
        review = User(username='local-review', display_name='local-review', role_id=1,
                      hashed_password=None, email=None, is_active=True, is_claimed=True,
                      onboarding_completed_at=now)
        untouched = User(username='Real nickname stays', role_id=2, hashed_password=None)
        db.add_all([review, untouched])
        db.flush()
        db.add(ExternalPlayerIdentity(user_id=review.id, source='bfmeladder',
            external_uuid=str(uuid5(NAMESPACE_URL, 'local-replay-acceptance:1')),
            current_nickname='local-review', verification_status='verified'))
        old = Clan(name='Existing clan stays', leader_id=review.id)
        db.add(old)
        db.flush()
        db.add(ClanMember(user_id=review.id, clan_id=old.id, joined_at=now-timedelta(days=30)))
        db.add(CampaignSeason(number=1, name='Existing season', status='active',
            starts_at=now-timedelta(days=20), rules_snapshot={'mechanics_version': 'cycle_v1', 'version': 1}))
        db.add(CampaignRuleSet(version=1, values=default_campaign_rule_values(), is_active=True, reason='Fixture'))
        from app.models.campaign_cycle import CampaignCycleRecord
        db.flush()
        db.add(CampaignCycleRecord(season_id=1, number=1, rule_version=1,
            starts_at=now-timedelta(days=2), preparation_at=now-timedelta(days=2),
            battles_registered=False, dependencies={}))
        # Existing connected map, with occupied land and excluded ports/fortresses.
        for n in range(1, 17):
            db.add(Territory(id=n, name=f'Existing map land {n}', region='Preview fixture',
                svg_path_data=f'M{n} 0L{n+1} 1Z', adjacent_territory_ids=[i for i in range(1, 17) if i != n],
                owner_clan_id=old.id if n == 16 else None, has_port=n == 14,
                stronghold_power=3 if n == 15 else 0, required_territories=5 if n == 15 else 0))
        db.flush()
        for n in range(1, 17):
            db.add(CycleTerritoryProfile(season_id=1, territory_id=n,
                base={'gold': 100, 'iron': 5, 'wood': 0, 'food': 0, 'mithril': 0}, profile_material='iron'))
        db.commit()
    engine.dispose()
    yield path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path, sql):
    with sqlite3.connect(path) as db:
        return db.execute(sql).fetchall()


def test_seed_has_strict_path_allowlist(preview):
    seed = seeder()
    assert seed.validate_database_path(preview) == preview.resolve()
    for path in (ROOT / 'preview.db', ROOT / '.tmp/preview.db',
                 ROOT / 'clanwar_local.db', preview.parent / 'other.db',
                 preview.parent / '../' / preview.parent.name / 'preview.db',
                 Path('/home/clanwar/apps/clanwar/shared/preview.db'),
                 Path('/home/clanwar/apps/clanwar-preview/shared/preview.db')):
        with pytest.raises(ValueError):
            seed.validate_database_path(path)
    with pytest.raises(ValueError):
        seed.validate_database_path(preview, allow_server_preview=True)


def test_seed_rejects_hardlinked_database(preview):
    seed = seeder()
    alias = preview.parent / 'hardlink.db'
    try:
        alias.hardlink_to(preview)
    except OSError:
        pytest.skip('Host forbids creating hardlinks')
    with pytest.raises(ValueError, match='link'):
        seed.seed_preview(preview, worker_disabled=True)
    alias.unlink()


@pytest.mark.parametrize('mutation', [
    "update external_player_identities set external_uuid='00000000-0000-0000-0000-000000000001'",
    "update users set role_id=2 where username='local-review'",
    "update users set hashed_password='not-synthetic' where username='local-review'",
    "update users set onboarding_completed_at=NULL where username='local-review'",
    "update campaign_seasons set rules_snapshot='{}'",
    'drop table cycle_market_caravans',
    'update territories set owner_clan_id=1',
    'delete from cycle_territory_profiles',
    'update campaign_cycles set battles_registered=1',
    "insert into campaign_cycle_plans (cycle_id,clan_id,revision,orders) values (1,1,1,'[]')",
])
def test_seed_preflight_never_writes_invalid_preview(preview, mutation):
    seed = seeder()
    with sqlite3.connect(preview) as db:
        db.execute(mutation)
    before = digest(preview)
    with pytest.raises(ValueError):
        seed.seed_preview(preview, worker_disabled=True)
    assert digest(preview) == before
    assert not list(preview.parent.glob('*.bak'))


def test_worker_acknowledgment_required(preview):
    before = digest(preview)
    with pytest.raises(ValueError, match='worker'):
        seeder().seed_preview(preview)
    assert digest(preview) == before


def test_seed_preserves_diplomacy_journal_of_unplayed_preview_cycle(preview):
    from app.models.cycle_diplomacy import CycleDiplomacyPair, CycleDiplomacyEvent
    engine = create_engine('sqlite:///' + preview.as_posix())
    with Session(engine) as db:
        other = Clan(name='Existing second clan', leader_id=2)
        db.add(other)
        db.flush()
        pair = CycleDiplomacyPair(season_id=1, clan_low_id=1, clan_high_id=other.id)
        db.add(pair)
        db.flush()
        db.add(CycleDiplomacyEvent(pair_id=pair.id, cycle_id=1, actor_clan_id=1,
            actor_user_id=1, kind='war_declared', occurred_at=datetime.now(timezone.utc), payload={}))
        db.commit()
    engine.dispose()
    journal = rows(preview, 'select * from cycle_diplomacy_events')
    seeder().seed_preview(preview, worker_disabled=True)
    assert rows(preview, 'select * from cycle_diplomacy_events') == journal
    assert rows(preview, 'select settled_at from campaign_cycles where id=1')[0][0]


def test_recent_worker_heartbeat_is_refused(preview):
    with sqlite3.connect(preview) as db:
        db.execute('insert into worker_heartbeats (worker_name, heartbeat_at, consecutive_failures) values (?, ?, ?)',
                   ('preview-worker', datetime.now(timezone.utc).replace(tzinfo=None).isoformat(' '), 0))
    before = digest(preview)
    with pytest.raises(ValueError, match='worker'):
        seeder().seed_preview(preview, worker_disabled=True)
    assert digest(preview) == before
    assert not list(preview.parent.glob('*.bak'))


def test_seed_reports_real_readiness_and_distinct_map_colors(preview):
    report = seeder().seed_preview(preview, worker_disabled=True)
    assert report['readiness']['can_request_scout'] is True
    assert report['readiness']['planning_editable'] is True
    assert report['readiness']['reinforcements_can_command'] is False
    assert report['readiness']['trade_quote_available'] is True
    colors = {c['map_color'] for c in report['clans']}
    assert len(colors) == 3 and None not in colors
    assert report['ownership'] == {str(t): c['id'] for c in report['clans'] for t in c['territory_ids']}


def test_seed_preserves_history_auth_and_map_and_refuses_second_run(preview):
    seed = seeder()
    before_users = rows(preview, 'select * from users order by id')
    before_map = rows(preview, 'select id,name,svg_path_data,adjacent_territory_ids from territories order by id')
    before_clan = rows(preview, 'select * from clans order by id')
    report = seed.seed_preview(preview, worker_disabled=True)
    assert report['phase'] == 'preparation'
    assert len(report['clans']) == 3
    assert rows(preview, 'select * from users where id<=2 order by id') == before_users
    assert rows(preview, 'select id,name,svg_path_data,adjacent_territory_ids from territories order by id') == before_map
    # The previous leader pointer is preserved; only the synthetic user's membership moves.
    assert rows(preview, 'select * from clans where id=1') == before_clan
    assert rows(preview, 'select count(*) from user_sessions') == [(0,)]
    assert rows(preview, 'select count(*) from users where hashed_password is not null') == [(0,)]
    assert rows(preview, 'select count(*) from cycle_market_caravans where delivered_at is null') == [(2,)]
    assert rows(preview, "select count(*) from cycle_market_offers where status='pending'") == [(2,)]
    assert rows(preview, 'select count(*)-count(distinct external_uuid) from external_player_identities') == [(0,)]
    backup = Path(report['backup'])
    assert backup.is_file()
    assert rows(backup, 'select * from users order by id') == before_users
    assert rows(backup, 'select * from clans order by id') == before_clan
    before = digest(preview)
    with pytest.raises(ValueError, match='already'):
        seed.seed_preview(preview, worker_disabled=True)
    assert digest(preview) == before
    assert len(list(preview.parent.glob('*.bak'))) == 1


def test_seed_rolls_back_even_after_market_savepoints(preview, monkeypatch):
    seed = seeder()
    from app.services.cycle_market_service import CycleMarketService
    original = CycleMarketService.accept

    def fail_after_accept(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError('Injected after escrow and caravan writes')

    monkeypatch.setattr(CycleMarketService, 'accept', fail_after_accept)
    before = digest(preview)
    with pytest.raises(RuntimeError, match='Injected'):
        seed.seed_preview(preview, worker_disabled=True)
    assert digest(preview) == before
    assert len(list(preview.parent.glob('*.bak'))) == 1


@pytest.mark.parametrize('mode', ['preparation', 'battle'])
def test_scenario_requires_seed_and_rejects_foreign_database(preview, mode):
    service = scenarios()
    before = digest(preview)
    with pytest.raises(ValueError, match='seed'):
        service.read_preview_scenario(preview)
    with pytest.raises(ValueError, match='seed'):
        service.switch_preview_scenario(preview, mode)
    with pytest.raises(ValueError):
        service.switch_preview_scenario(ROOT / 'clanwar_local.db', mode)
    assert digest(preview) == before


def test_scenario_preserves_plan_freezes_and_same_mode_never_resets(preview):
    report = seeder().seed_preview(preview, worker_disabled=True)
    service = scenarios()
    assert service.read_preview_scenario(preview)['mode'] == 'preparation'
    before = digest(preview)
    assert service.switch_preview_scenario(preview, 'preparation', confirm_reset=True)['mode'] == 'preparation'
    assert digest(preview) == before
    plans = rows(preview, f'select clan_id,orders from campaign_cycle_plans where cycle_id={report["cycle_id"]} order by clan_id')
    old_clans = rows(preview, 'select * from clans order by id')
    wallets = rows(preview, 'select id,season_id,clan_id,wallet,relics,active_relics,starters_chosen from cycle_economy_states order by id')
    history = rows(preview, f'select * from campaign_cycles where id!={report["cycle_id"]} order by id')
    view = service.switch_preview_scenario(preview, 'battle')
    assert view['mode'] == view['phase'] == 'battle'
    assert view['cycle_id'] == report['cycle_id']
    assert view['reinforcements_can_command']
    assert view['available_reserve_user_ids']
    assert view['own_targets'] and view['allied_targets']
    assert rows(preview, f'select clan_id,orders from campaign_cycle_plans where cycle_id={report["cycle_id"]} and orders!=\'[]\' order by clan_id') == plans
    assert rows(preview, 'select * from clans order by id') == old_clans
    # Normal reveal increments wallet CAS revisions without changing any funds or relics.
    assert rows(preview, 'select id,season_id,clan_id,wallet,relics,active_relics,starters_chosen from cycle_economy_states order by id') == wallets
    assert rows(preview, f'select * from campaign_cycles where id!={report["cycle_id"]} order by id') == history
    before = digest(preview)
    assert service.read_preview_scenario(preview)['mode'] == 'battle'
    service.switch_preview_scenario(preview, 'battle', confirm_reset=True)
    assert digest(preview) == before


def test_scenario_confirmed_reset_is_demo_only_preserves_trade_and_history(preview):
    report = seeder().seed_preview(preview, worker_disabled=True)
    service = scenarios()
    service.switch_preview_scenario(preview, 'battle')
    before = digest(preview)
    with pytest.raises(ValueError, match='confirm_reset'):
        service.switch_preview_scenario(preview, 'preparation')
    assert digest(preview) == before
    protected = ['users', 'clans', 'clan_members', 'clan_membership_periods', 'territories',
                 'territory_ownership_history', 'cycle_economy_states', 'cycle_market_offers',
                 'cycle_market_caravans', 'campaign_rule_sets', 'campaign_seasons']
    saved = {table: rows(preview, f'select * from {table}') for table in protected}
    history = rows(preview, f'select * from cycle_territory_battles where cycle_id={report["history_cycle_id"]}')
    view = service.switch_preview_scenario(preview, 'preparation', confirm_reset=True)
    assert view['mode'] == view['phase'] == 'preparation'
    assert view['planning_editable'] and view['can_request_scout']
    assert not view['reinforcements_can_command']
    assert view['trade_quote']
    assert rows(preview, f'select count(*) from cycle_territory_battles where cycle_id={report["cycle_id"]}') == [(0,)]
    assert rows(preview, f'select * from cycle_territory_battles where cycle_id={report["history_cycle_id"]}') == history
    assert {table: rows(preview, f'select * from {table}') for table in protected} == saved
    second = service.switch_preview_scenario(preview, 'battle')
    assert second['available_reserve_user_ids'] and second['allied_targets']


def test_scenario_rejects_non_demo_plan_and_rolls_back_failed_reveal(preview, monkeypatch):
    report = seeder().seed_preview(preview, worker_disabled=True)
    service = scenarios()
    from app.services.cycle_reveal_service import CycleRevealService

    original = CycleRevealService.reveal

    def fail_after_reveal(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError('Injected reveal failure')

    monkeypatch.setattr(CycleRevealService, 'reveal', fail_after_reveal)
    before = digest(preview)
    with pytest.raises(RuntimeError, match='Injected'):
        service.switch_preview_scenario(preview, 'battle')
    assert digest(preview) == before
    assert service.read_preview_scenario(preview)['mode'] == 'preparation'


def test_scenario_refuses_foreign_target_before_reveal(preview):
    import json
    report = seeder().seed_preview(preview, worker_disabled=True)
    with sqlite3.connect(preview) as db:
        orders = json.loads(db.execute('select orders from campaign_cycle_plans where cycle_id=? and clan_id=?',
            (report['cycle_id'], report['clans'][0]['id'])).fetchone()[0])
        orders[0]['territory_id'] = 16
        db.execute('update campaign_cycle_plans set orders=? where cycle_id=? and clan_id=?',
                   (json.dumps(orders), report['cycle_id'], report['clans'][0]['id']))
    before = digest(preview)
    view = scenarios().read_preview_scenario(preview)
    assert view['mode'] == 'preparation'
    assert view['can_switch_to_battle'] is False
    assert 'owned' in view['disableReason']
    assert digest(preview) == before
    with pytest.raises(ValueError, match='owned'):
        scenarios().switch_preview_scenario(preview, 'battle')
    assert digest(preview) == before


def test_scenario_status_survives_unaffordable_pending_trade(preview):
    import json
    report = seeder().seed_preview(preview, worker_disabled=True)
    with sqlite3.connect(preview) as db:
        wallet = {key: '0' for key in ('gold', 'iron', 'wood', 'food', 'mithril')}
        db.execute('update cycle_economy_states set wallet=? where season_id=? and clan_id=?',
                   (json.dumps(wallet), report['season_id'], report['clans'][0]['id']))
    before = digest(preview)
    view = scenarios().read_preview_scenario(preview)
    assert view['mode'] == 'preparation' and view['planning_editable']
    assert view['trade_quote'] is None and view['quote_available'] is False
    assert view['trade_disabled_reason']
    assert view['can_switch_to_battle']
    assert digest(preview) == before
def test_real_authenticated_api_trade_plans_scout_and_help(preview, monkeypatch):
    """PREVIEW_CAMPAIGN_SOURCE optionally exercises a read-only clone of the real preview."""
    import json
    import os
    from decimal import Decimal
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.v1 import cycle_campaign, cycle_operations, cycle_market, territories
    from app.config import settings
    from app.database import get_db
    from app.models.campaign_cycle import CampaignCycleRecord
    from app.models.cycle_economy import CycleEconomyState
    from app.models.cycle_market import CycleMarketCaravan
    from app.services.campaign_cycle_store import CampaignCycleStore
    from app.services.cycle_reveal_service import CycleRevealService
    from app.services.session_service import SessionService

    seed = seeder()
    source = os.environ.get('PREVIEW_CAMPAIGN_SOURCE')
    source_hash = None
    if source:
        original = seed.validate_database_path(source)
        source_hash = digest(original)
        with sqlite3.connect(original.as_uri()+'?mode=ro', uri=True) as src, sqlite3.connect(preview) as dst:
            src.backup(dst)
    report = seed.seed_preview(preview, worker_disabled=True)
    # Keep the seed-only artifact intact: all authentication and API commands run on another disposable copy.
    assert not rows(preview, 'select id from campaign_cycles where settled_at is null and id != ' + str(report['cycle_id']))
    api_folder = preview.parent / 'api-smoke'
    api_folder.mkdir()
    api_copy = api_folder / 'preview.db'
    with sqlite3.connect(preview.as_uri()+'?mode=ro', uri=True) as src, sqlite3.connect(api_copy) as dst:
        src.backup(dst)
    engine = create_engine('sqlite:///' + api_copy.as_posix(), connect_args={'check_same_thread': False})
    app = FastAPI()
    app.include_router(cycle_campaign.router, prefix='/api/v1/campaign')
    app.include_router(territories.router, prefix='/api/v1/territories')

    def database():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    main, ally, neutral = report['clans']
    cycle_id = report['cycle_id']
    root = '/api/v1/campaign/cycles'
    base = f'{root}/{cycle_id}/clans/{main["id"]}'
    market = f'{root}/market/cycles/{cycle_id}/clans/{main["id"]}'
    evidence = []

    def check(response):
        evidence.append({'method': response.request.method, 'path': response.request.url.path,
                         'status': response.status_code})
        assert response.status_code == 200, response.text
        return response.json()

    with Session(engine) as db:
        token = SessionService().issue(db, db.get(User, report['review_user_id'])).token
        ally_token = SessionService().issue(db, db.get(User, ally['leader_user_id'])).token
        neutral_token = SessionService().issue(db, db.get(User, neutral['leader_user_id'])).token

    with TestClient(app) as client:
        assert client.get(root + '/current').status_code == 401
        client.cookies.set(settings.SESSION_COOKIE_NAME, token)
        assert check(client.get(root + '/current'))['cycle']['id'] == cycle_id
        treasury = check(client.get(f'{root}/economy/seasons/{report["season_id"]}/clans/{main["id"]}/context'))
        assert treasury['ready'] and treasury['can_trade'] and len(treasury['lands']) == 3
        planning = check(client.get(base + '/planning'))
        assert planning['editable'] and len([u for u in planning['members'] if u['eligible']]) == 6
        assert planning['attack_routes']
        assert len(planning['defence_targets']) == 3
        map_rows = check(client.get('/api/v1/territories/'))
        by_id = {t['id']: t for t in map_rows}
        for clan in report['clans']:
            for tid in clan['territory_ids']:
                assert by_id[tid]['owner_clan_id'] == clan['id']
                assert by_id[tid]['owner_clan_name'] == clan['name']
                assert by_id[tid]['owner_clan_map_color'] == clan['map_color']
        check(client.put(base + '/plan', json={'expected_revision': planning['plan']['revision'],
                                             'orders': planning['plan']['orders']}))
        prep = check(client.get(base + '/preparation'))
        assert prep['scout']['can_request']
        scout = check(client.post(base + '/scout', json={'territory_id': report['battle_territory_ids'][0],
            'scout_user_id': prep['scout']['players'][0]['user_id'], 'expected_revision': prep['scout']['wallet_revision']}))
        assert check(client.get(base + f'/scout/{scout["id"]}/report')) == {'report': None}
        help_context = check(client.get(base + '/reinforcements/context'))
        assert help_context['phase'] == 'preparation' and not help_context['can_command']
        own = check(client.get(market))
        assert len(own['caravans']) == 1 and own['caravans'][0]['delivered_at'] is None
        incoming_url = market + f'/offers/{report["incoming_offer_id"]}'
        quote = check(client.get(incoming_url + '/quote'))
        assert quote['travel_hours'] > 0
        readiness = {'can_request_scout': prep['scout']['can_request'],
                     'planning_editable': planning['editable'], 'trade_quote': quote,
                     'reinforcements_can_command': help_context['can_command'],
                     'ownership_colors': {c['name']: c['map_color'] for c in report['clans']}}
        with Session(engine) as db:
            before_wallet = dict(db.query(CycleEconomyState).filter_by(
                season_id=report['season_id'], clan_id=main['id']).one().wallet)
        accepted = check(client.post(incoming_url + '/accept', json={
            **{k: v for k, v in quote.items() if k.startswith('expected_')}, 'command_id': 'api-smoke:accept'}))
        assert accepted['status'] == 'accepted'
        with Session(engine) as db:
            wallet = db.query(CycleEconomyState).filter_by(season_id=report['season_id'], clan_id=main['id']).one()
            assert Decimal(wallet.wallet['iron']) == Decimal(before_wallet['iron']) - 10
            assert Decimal(wallet.wallet['gold']) == Decimal(before_wallet['gold']) - Decimal(quote['fee_gold'])
            assert wallet.wallet['wood'] == before_wallet['wood']  # Not delivered prematurely.
            rev = wallet.revision
            assert db.query(CycleMarketCaravan).count() == 4
        created = check(client.post(market + '/offers', json={'command_id': 'api-smoke:create',
            'expected_wallet_revision': rev, 'target_clan_id': ally['id'],
            'offered': {'food': '3'}, 'requested': {'iron': '2'}}))
        assert created['status'] == 'pending'
        client.cookies.set(settings.SESSION_COOKIE_NAME, neutral_token)
        neutral_market = market.replace(f'/clans/{main["id"]}', f'/clans/{neutral["id"]}')
        outgoing_url = neutral_market + f'/offers/{report["outgoing_offer_id"]}'
        quote = check(client.get(outgoing_url + '/quote'))
        check(client.post(outgoing_url + '/accept', json={
            **{k: v for k, v in quote.items() if k.startswith('expected_')}, 'command_id': 'api-smoke:accept-outgoing'}))
        client.cookies.set(settings.SESSION_COOKIE_NAME, token)
        history = check(client.get(f'{root}/battles/{report["history_battle_id"]}'))
        assert {Decimal(s['score']) for s in history['sides']} == {Decimal(120), Decimal(-40)}

        # Exercise the private helper on the disposable copy, at real wall-clock time.
        switched = scenarios().switch_preview_scenario(api_copy, 'battle')
        assert switched['mode'] == 'battle' and switched['available_reserve_user_ids']
        scout_report = check(client.get(base + f'/scout/{scout["id"]}/report'))
        assert scout_report == {'report': {'enemy_squads': [2]}}
        ctx = check(client.get(base + '/reinforcements/context'))
        assert ctx['can_command'] and ctx['allied_targets']
        assert any(r['status'] == 'mapped' for r in ctx['route_previews'])
        target = ctx['allied_targets'][0]['territory_id']
        request_id = ctx['allied_targets'][0]['request_id']
        own_target = ctx['help_targets'][0]
        check(client.post(base + '/reinforcements/requests', json={'request_id': 'api-smoke:own-help',
            'territory_id': own_target, 'expected_revision': ctx['state']['revision']}))
        ctx = check(client.get(base + '/reinforcements/context'))
        sent = check(client.post(base + '/reinforcements/dispatches', json={
            'dispatch_id': 'api-smoke:dispatch', 'request_id': request_id, 'recipient_clan_id': ally['id'],
            'territory_id': target, 'origin_territory_id': main['territory_ids'][0],
            'player_user_ids': main['reserve_user_ids'][:1], 'expected_revision': ctx['state']['revision']}))
        dispatch = next(d for d in sent['dispatches'] if d['id'] == 'api-smoke:dispatch')
        assert dispatch['route']['status'] == 'mapped'
        assert datetime.fromisoformat(dispatch['arrives_at']) - datetime.fromisoformat(dispatch['sent_at']) == timedelta(hours=24)
        reset = scenarios().switch_preview_scenario(api_copy, 'preparation', confirm_reset=True)
        assert reset['can_request_scout'] and reset['planning_editable']
    engine.dispose()
    if source:
        assert digest(original) == source_hash
    (preview.parent / 'seed-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (preview.parent / 'api-smoke-report.json').write_text(json.dumps({
        'source_unchanged': bool(source), 'seed_database': str(preview), 'api_database': str(api_copy),
        'authentication': 'real server-side cookie sessions, only on disposable API copy',
        'rights_overrides': False, 'requests': evidence,
        'readiness': readiness,
        'scout_report_in_battle': scout_report,
        'help_clock': 'private helper retimes the whole demo preparation; real API time, no time mock',
        'reset': reset}, indent=2), encoding='utf-8')
