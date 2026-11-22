import asyncio
from contextlib import nullcontext
from datetime import timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.v1.campaign_guard import require_campaign_running
from app.core.campaign_mode import cycle_owns_campaign, require_legacy_economy
from app.core.exceptions import InsufficientPermissionsException
from app.core.time import utc_now
from app.database import get_db
from app.models.campaign import CampaignSeason, CampaignSettings
from app.models.clan import Clan, ClanMember
from app.models.market import MarketOffer
from app.models.operation import ResourceLedgerEntry
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.models.user import User
from app.models.war import ClanWar
from app.services.campaign_pause_service import CampaignPauseService
from app.services.clan_economy_service import ClanEconomyService
from app.services.market_service import ClanMarketService
from app.services.scheduler_service import CampaignWorker
from tests.test_legacy_economy_isolation import legacy_world, create_offer, add_season


def close_season(db, season):
    season.status = 'completed'
    season.ends_at = utc_now()
    db.commit()


def snapshot(db, *models):
    return {
        model.__name__: [
            {column.name: getattr(row, column.name) for column in model.__table__.columns}
            for row in db.query(model).order_by(model.id)
        ] for model in models
    }


@pytest.mark.parametrize('status,active,blocked', [
    (None, False, False), ('active', False, False), ('completed', False, True),
    ('finished', False, False), ('completed', True, False),
])
def test_effective_pause_blocks_only_completed_latest_without_active(db, status, active, blocked):
    if status:
        add_season(db, status=status, cycle=False)
    if active:
        add_season(db, number=2, cycle=False)
    assert CampaignPauseService.is_paused(db) is blocked
    assert cycle_owns_campaign(db) is False
    if blocked:
        with pytest.raises(HTTPException) as error:
            require_campaign_running(db)
        assert error.value.status_code == 409
        assert 'Межсезонье' in error.value.detail
        with pytest.raises(InsufficientPermissionsException, match='Межсезонье'):
            require_legacy_economy(db)
    else:
        require_campaign_running(db)
        require_legacy_economy(db)
    assert db.query(CampaignSettings).count() == 0


def test_newer_uncompleted_season_is_not_interseason(db):
    add_season(db, status='completed', cycle=False)
    add_season(db, number=2, status='scheduled', cycle=False)
    assert CampaignPauseService.is_paused(db) is False


@pytest.mark.parametrize('mutation', ['purchase', 'loadout', 'upgrade', 'create', 'accept', 'cancel', 'reset'])
def test_interseason_denies_direct_economy_and_market_mutations(db, legacy_world, mutation):
    users, clans, territories, asset = legacy_world
    season = add_season(db, cycle=False)
    offer = create_offer(db, legacy_world)
    close_season(db, season)
    models = (Clan, ClanMember, User, Territory, ResourceLedgerEntry, MarketOffer, CampaignSeason)
    before = snapshot(db, *models)
    economy, market = ClanEconomyService(), ClanMarketService()
    commands = {
        'purchase': lambda: economy.purchase_asset(db, clans[0].id, asset.id, users[0]),
        'loadout': lambda: economy.update_relic_loadout(db, clans[0].id, [], users[0]),
        'upgrade': lambda: economy.upgrade_territory(db, territories[0].id, 'population', 1, users[0]),
        'create': lambda: create_offer(db, legacy_world),
        'accept': lambda: market.accept_offer(db, offer_id=offer.id,
                                             accepter_clan_id=clans[1].id, current_user=users[1]),
        'cancel': lambda: market.cancel_offer(db, offer_id=offer.id, current_user=users[0]),
        'reset': lambda: economy.start_new_season(db, 500, actor_user_id=users[0].id),
    }
    with pytest.raises(InsufficientPermissionsException, match='Межсезонье'):
        commands[mutation]()
    assert snapshot(db, *models) == before


@pytest.mark.parametrize('path', ['settle_clan', 'settle_all', 'prepare', 'territory_economy', 'clan_economy', 'territories_get'])
def test_interseason_economy_reads_do_not_backfill_or_accrue(db, legacy_world, path):
    _, clans, territories, _ = legacy_world
    add_season(db, status='completed', cycle=False)
    clan, territory = clans[0], territories[0]
    clan.last_economy_tick = utc_now() - timedelta(days=3)
    clan.resources = 12345
    territory.resource_type = 'legacy-unknown'
    territory.resource_output = 0
    territory.strategic_value = 99
    territory.adjacent_territory_ids = [] if path == 'territories_get' else None
    db.commit()
    models = (Clan, ClanMember, User, Territory, TerritoryOwnershipHistory, ResourceLedgerEntry, CampaignSeason)
    before = snapshot(db, *models)
    economy = ClanEconomyService()
    commands = {
        'settle_clan': lambda: economy.settle_clan(db, clan),
        'settle_all': lambda: economy.settle_all(db),
        'prepare': lambda: economy.prepare_territory(db, territory),
        'territory_economy': lambda: economy.get_territory_economy(territory, db),
        'clan_economy': lambda: economy.get_clan_economy(db, clan.id),
    }
    if path == 'territories_get':
        from app.api.v1.territories import router
        app = FastAPI()
        app.include_router(router, prefix='/territories')
        app.dependency_overrides[get_db] = lambda: db
        response = TestClient(app).get('/territories/')
        assert response.status_code == 200, response.text
        assert response.json()[0]['resource_type'] == 'legacy-unknown'
    else:
        commands[path]()
    db.commit()
    assert snapshot(db, *models) == before
    assert db.query(CampaignSettings).count() == 0


@pytest.mark.parametrize('cycle', [False, True])
def test_current_exposes_explicit_interseason_without_rewriting_mechanics(db, cycle):
    from app.api.v1.cycle_campaign import current_cycle
    season = add_season(db, status='completed', cycle=cycle)
    data = current_cycle(db=db, _user=None)
    assert data['interseason'] is True
    assert data['archived_season_id'] == season.id
    assert data['mechanics_version'] == ('cycle_v1' if cycle else 'legacy')
    assert data['season_status'] == 'completed'
    assert data['territory_battles'] == []
    assert db.query(CampaignSeason).count() == 1


@pytest.mark.parametrize('status', [None, 'active', 'scheduled'])
def test_current_bootstrap_and_active_are_not_interseason(db, status):
    from app.api.v1.cycle_campaign import current_cycle
    if status:
        add_season(db, status=status, cycle=False)
    data = current_cycle(db=db, _user=None)
    assert data.get('interseason', False) is False
    assert data.get('archived_season_id') is None
    assert data['mechanics_version'] == 'legacy'


def accepted_offer(db, world):
    users, clans, _, _ = world
    season = add_season(db, cycle=False)
    offer = create_offer(db, world)
    ClanMarketService().accept_offer(db, offer_id=offer.id,
                                    accepter_clan_id=clans[1].id, current_user=users[1])
    close_season(db, season)
    return offer


@pytest.mark.parametrize('due', [False, True])
def test_accepted_cargo_survives_closure_and_delivers_once_at_eta(db, legacy_world, due):
    _, clans, _, _ = legacy_world
    offer = accepted_offer(db, legacy_world)
    offer.eta = utc_now() + timedelta(hours=-1 if due else 1)
    for caravan in offer.caravans:
        caravan.eta = offer.eta
    db.commit()
    gold = [clan.gold for clan in clans]
    service = ClanMarketService()
    assert service.settle_due(db) == int(due)
    assert offer.status == ('completed' if due else 'in_transit')
    assert all(row.status == ('delivered' if due else 'traveling') for row in offer.caravans)
    assert [clan.gold for clan in clans] == gold
    assert clans[0].iron == (24 if due else 20)
    assert clans[1].wood == (25 if due else 20)
    assert service.settle_due(db) == 0
    assert db.query(CampaignSeason).count() == 1


def test_new_active_season_still_rejects_old_escrow_without_credit(db, legacy_world):
    _, clans, _, _ = legacy_world
    offer = accepted_offer(db, legacy_world)
    add_season(db, number=2, cycle=False)
    before = snapshot(db, Clan)
    assert ClanMarketService().settle_due(db) == 0
    assert offer.status == 'failed'
    assert snapshot(db, Clan) == before


def test_interseason_market_quote_is_unavailable_without_mutation(db, legacy_world):
    _, clans, _, _ = legacy_world
    season = add_season(db, cycle=False)
    offer = create_offer(db, legacy_world)
    close_season(db, season)
    quote = ClanMarketService().quote_for_clan(db, offer, clans[1].id)
    assert quote['available'] is False
    assert quote['reason_code'] == 'interseason'
    assert offer.status == 'open'


@pytest.mark.parametrize('read', ['expire', 'list'])
def test_interseason_market_reads_leave_unaccepted_offers_unchanged(db, legacy_world, read):
    _, clans, _, _ = legacy_world
    season = add_season(db, cycle=False)
    offer = create_offer(db, legacy_world)
    offer.expires_at = utc_now() - timedelta(days=1)
    close_season(db, season)
    before = snapshot(db, MarketOffer, Clan, ResourceLedgerEntry)
    market = ClanMarketService()
    if read == 'expire':
        assert market.expire_open_offers(db) == 0
    else:
        data = market.list_market(db, clans[1].id)
        assert data['offers'][0]['quote']['reason_code'] == 'interseason'
    db.commit()
    assert snapshot(db, MarketOffer, Clan, ResourceLedgerEntry) == before


@pytest.mark.parametrize('cycle', [False, True])
def test_interseason_worker_keeps_personal_imports_and_delivers_accepted_cargo(db, legacy_world, monkeypatch, cycle):
    import app.services.scheduler_service as scheduler
    from app.models.match import Match

    offer = accepted_offer(db, legacy_world)
    if cycle:
        db.query(CampaignSeason).one().rules_snapshot = {'mechanics_version': 'cycle_v1'}
    offer.eta = utc_now() - timedelta(seconds=1)
    for caravan in offer.caravans:
        caravan.eta = offer.eta
    db.add(ClanWar(territory_id=legacy_world[2][0].id,
                   attacking_clan_id=legacy_world[1][0].id,
                   war_type='neutral_capture', status='active', ends_at=offer.eta))
    db.commit()
    before = snapshot(db, User, ClanMember, Territory)
    events = []

    class Ladder:
        async def fetch_and_save_matches(self, session, limit):
            events.append('personal-import')
            session.add(Match(match_id='interseason-personal', winner_player='A',
                              loser_player='B', winner_faction='Gondor',
                              loser_faction='Mordor', match_date=utc_now()))
            session.commit()
            return 1

    class Backfill:
        async def process_pending(self, session):
            events.append('personal-backfill')
            return 0

    class ForbiddenEconomy:
        def settle_all(self, session):
            pytest.fail('Interseason must not invoke seasonal income')

    class ForbiddenIntake:
        def ingest_pending(self, session, *, now):
            pytest.fail('Interseason must not ingest new seasonal battle contributions')

    monkeypatch.setattr(scheduler, 'SessionLocal', lambda: nullcontext(db))
    monkeypatch.setattr(scheduler, 'BFMELadderService', Ladder)
    monkeypatch.setattr(scheduler, 'ArenaMatchBackfillService', Backfill)
    monkeypatch.setattr(scheduler, 'ClanEconomyService', ForbiddenEconomy)
    monkeypatch.setattr(scheduler, 'CycleArenaIngestionService', ForbiddenIntake)
    worker = CampaignWorker()
    assert asyncio.run(worker.run_cycle()) == 1
    assert events == ['personal-import', 'personal-backfill']
    assert db.query(Match).filter_by(match_id='interseason-personal').count() == 1
    assert offer.status == 'completed'
    assert snapshot(db, User, ClanMember, Territory) == before
    assert worker._next_war_end(db) is None
    assert asyncio.run(worker._complete_due_wars()) == 0
    assert db.query(ClanWar).one().status == 'active'
    assert db.query(CampaignSeason).count() == 1


@pytest.mark.parametrize('command', ['pause', 'resume'])
def test_interseason_does_not_create_pause_calendar(db, legacy_world, command):
    users, _, _, _ = legacy_world
    add_season(db, status='completed', cycle=False)
    with pytest.raises(ValueError, match='Межсезонье'):
        getattr(CampaignPauseService(), command)(db, actor_user_id=users[0].id, reason='test')
    assert db.query(CampaignSettings).count() == 0


@pytest.mark.parametrize('action', ['purchase', 'loadout', 'upgrade', 'create', 'accept', 'cancel', 'war', 'reset'])
def test_interseason_api_seasonal_mutations_return_conflict(db, legacy_world, action):
    from app.api.v1.clans import router as clans_router
    from app.api.v1.territories import router as territories_router
    from app.api.v1.wars import router as wars_router
    from app.core.auth import get_current_active_user, get_onboarded_active_user, get_current_admin_user

    users, clans, territories, asset = legacy_world
    season = add_season(db, cycle=False)
    offer = create_offer(db, legacy_world)
    close_season(db, season)
    app = FastAPI()
    app.include_router(clans_router)
    app.include_router(territories_router, prefix='/territories')
    app.include_router(wars_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: users[0]
    app.dependency_overrides[get_onboarded_active_user] = lambda: users[0]
    app.dependency_overrides[get_current_admin_user] = lambda: users[0]
    requests = {
        'purchase': ('post', f'/clans/{clans[0].id}/assets/purchase', {'asset_id': asset.id}),
        'loadout': ('put', f'/clans/{clans[0].id}/assets/loadout', {'asset_ids': []}),
        'upgrade': ('post', f'/territories/{territories[0].id}/upgrade', {'upgrade_type': 'population'}),
        'create': ('post', '/clans/market/offers', {'creator_clan_id': clans[0].id,
                   'give_resource': 'wood', 'give_amount': 1, 'receive_resource': 'iron', 'receive_amount': 1}),
        'accept': ('post', f'/clans/market/offers/{offer.id}/accept', {'accepter_clan_id': clans[1].id}),
        'cancel': ('post', f'/clans/market/offers/{offer.id}/cancel', {}),
        'war': ('post', '/wars/', {'territory_id': territories[1].id,
                'squad_member_ids': [users[0].id], 'warlord_user_id': users[0].id, 'expected_rule_version': 1}),
        'reset': ('post', '/territories/season/start', {'starting_influence': 500}),
    }
    before = snapshot(db, Clan, ClanMember, User, Territory, MarketOffer, ResourceLedgerEntry, CampaignSeason)
    method, path, payload = requests[action]
    response = getattr(TestClient(app), method)(path, json=payload)
    assert response.status_code == 409, response.text
    assert 'Межсезонье' in response.json()['detail']
    assert snapshot(db, Clan, ClanMember, User, Territory, MarketOffer, ResourceLedgerEntry, CampaignSeason) == before


def test_interseason_real_import_accounts_and_membership_stay_available(db, legacy_world):
    from app.models.achievement import Achievement, UserAchievement
    from app.models.clan import ClanInvite, ClanMembershipPeriod
    from app.models.match import Match
    from app.schemas.user import UserCreate
    from app.services.clan_service import ClanService
    from app.services.ladder_service import BFMELadderService
    from app.services.user_service import UserService

    users, clans, _, _ = legacy_world
    add_season(db, status='completed', cycle=False)
    achievement = Achievement(name='personal-before-cutover', description='Preserved',
                              icon='fa-trophy', category='combat', requirement_type='wins',
                              requirement_value=1)
    db.add(achievement)
    db.flush()
    db.add(UserAchievement(user_id=users[0].id, achievement_id=achievement.id,
                           progress=1, is_completed=True, completed_at=utc_now()))
    db.commit()
    before = snapshot(db, Clan, UserAchievement)
    service = UserService()
    newcomer = service.create_user(db, UserCreate(username='InterseasonNewPlayer',
                                    email='interseason@example.org', password='interseason-test-password'))
    invite = ClanInvite(clan_id=clans[0].id, inviter_id=users[0].id, invitee_id=newcomer.id)
    db.add(invite)
    db.commit()
    assert ClanService().respond_to_invite(db, invite.id, newcomer.id, 'accepted') is True
    assert db.query(ClanMember).filter_by(user_id=newcomer.id, clan_id=clans[0].id).one()
    assert db.query(ClanMembershipPeriod).filter_by(user_id=newcomer.id, ended_at=None).one()
    assert BFMELadderService()._save_match_to_db(db, 'interseason-real-import',
        [(newcomer.username, 'Gondor')], [('InterseasonOpponent', 'Mordor')],
        utc_now().strftime('%d.%m.%Y'), duration='20:00') is True
    assert db.query(Match).filter_by(match_id='interseason-real-import').one()
    stats = service.get_user_statistics(db, newcomer.username)
    assert stats['total_matches'] == 1
    assert stats['wins'] == 1
    assert snapshot(db, Clan, UserAchievement) == before
    assert db.query(Clan).count() == 2
    assert db.query(ClanMember).count() == 3
    assert db.query(CampaignSeason).count() == 1
