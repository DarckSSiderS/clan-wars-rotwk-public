import pytest
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord, CampaignCyclePlan
from app.services.cycle_map_service import CycleMapService
from app.models.cycle_economy import CycleTerritoryUpgrade
from app.models.cycle_income import CycleTerritoryProfile
from tests.test_cycle_reinforcement_store import world, initialize, request, send, T


def test_map_names_land_owner_attackers_and_only_real_revealed_origins(db, world):
    from app.models.territory import Territory
    users, clans, land, cycle = world
    source = Territory(name='Attack origin', region='Test', svg_path_data='M0 0', owner_clan_id=clans[2].id)
    db.add(source); db.flush()
    plan = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id, clan_id=clans[2].id).one()
    plan.orders=[{**o, 'source_id':source.id, 'route':'land'} if o['kind']=='attack' else o for o in plan.orders]
    db.flush()
    initialize(db, world)
    data=CycleMapService().read(db,cycle_id=cycle.id,actor_user_id=users[0].id,now=T)
    battle=data['battles'][0]
    assert battle['territory_name']==land.name and battle['owner_clan_id']==clans[1].id
    assert battle['owner_clan_name']==clans[1].name and battle['status']=='contested'
    assert {s['clan_id']:s['role'] for s in battle['sides']}=={clans[1].id:'defender',clans[2].id:'attacker'}
    assert data['attack_routes']==[dict(clan_id=clans[2].id,clan_name=clans[2].name,map_color=clans[2].map_color,
        source_territory_id=source.id,source_territory_name=source.name,
        target_territory_id=land.id,target_territory_name=land.name,route='land',player_count=1)]
    assert not any('player_user_ids' in route or 'uuid' in route for route in data['attack_routes'])


def test_map_help_request_and_dispatch_have_human_names_without_leaking_requests(db, world):
    users,clans,land,cycle=world
    initialize(db,world); request(db,world)
    service=CycleMapService()
    own=service.read(db,cycle_id=cycle.id,actor_user_id=users[0].id,now=T)
    help_request=own['requests'][0]
    assert help_request['clan_name']==clans[1].name and help_request['territory_name']==land.name
    assert service.read(db,cycle_id=cycle.id,actor_user_id=users[5].id,now=T)['requests']==[]
    send(db,world)
    dispatch=service.read(db,cycle_id=cycle.id,actor_user_id=users[7].id,now=T)['dispatches'][0]
    assert dispatch['sender_clan_name']==clans[0].name and dispatch['recipient_clan_name']==clans[1].name
    assert dispatch['territory_name']==land.name and dispatch['player_count']==1


def test_map_is_read_only_and_clanless_users_never_see_private_reserves(db, world):
    users, _, _, cycle = world
    service = CycleMapService()
    before = service.read(db, cycle_id=cycle.id, actor_user_id=users[7].id, now=T)
    assert not before['ready']
    assert before['attack_routes'] == before['clans'] == before['battles'] == []
    initialize(db, world)
    data = service.read(db, cycle_id=cycle.id, actor_user_id=users[7].id, now=T)
    assert data['ready'] and data['clan_id'] is None
    assert not data['can_command'] and not data['help_targets']
    assert data['ambushes'] == []
    assert 'reserves' not in data and 'player_identities' not in data and 'uuid' not in str(data)


def test_map_requests_visible_to_allies_and_ambush_only_after_trigger(db, world):
    users, clans, land, cycle = world
    initialize(db, world)
    request(db, world)
    service = CycleMapService()
    data = service.read(db, cycle_id=cycle.id, actor_user_id=users[0].id, now=T)
    assert data['allied_targets'][0]['request_id'] == 'q'
    enemy = service.read(db, cycle_id=cycle.id, actor_user_id=users[5].id, now=T)
    assert enemy['requests'] == []
    send(db, world)
    after = service.read(db, cycle_id=cycle.id, actor_user_id=users[0].id, now=T)
    assert after['allied_targets'] == []
    assert after['ambushes'][0]['clan_id'] == clans[2].id
    assert after['dispatches'][0]['territory_id'] == land.id
    assert after['dispatches'][0]['arrives_at']


def test_map_rejects_archived_or_superseded_cycles(db, world):
    users, _, _, cycle = world
    db.get(CampaignSeason, cycle.season_id).status = 'completed'
    db.flush()
    with pytest.raises(ValueError):
        CycleMapService().read(db, cycle_id=cycle.id, actor_user_id=users[0].id, now=T)


def test_map_projects_only_current_season_income_and_three_level_development_without_initializing(db, world):
    users, _, land, cycle = world
    db.add(CycleTerritoryProfile(season_id=cycle.season_id, territory_id=land.id,
        base={'gold': '150', 'iron': '4', 'wood': '0', 'food': '0', 'mithril': '0'}, profile_material='iron'))
    db.add(CycleTerritoryUpgrade(season_id=cycle.season_id, territory_id=land.id,
        levels={'gold': 2, 'profile': 1, 'fortification': 3, 'offense': 1}))
    db.flush()
    before = db.query(CycleTerritoryUpgrade).count()
    data = CycleMapService().read(db, cycle_id=cycle.id, actor_user_id=users[7].id, now=T)
    assert not data['ready']
    entry = next(item for item in data['territories'] if item['territory_id'] == land.id)
    assert entry['daily_income'] == {'gold': '265', 'iron': '6', 'wood': '0', 'food': '0', 'mithril': '0'}
    assert entry['levels']['fortification'] == 3
    assert entry['max_level'] == 3
    assert 'wallet' not in str(data) and 'relics' not in str(data)
    assert db.query(CycleTerritoryUpgrade).count() == before


def test_map_distinguishes_unattacked_defence_and_neutral_multiclan_claims(db, world):
    from app.models.cycle_battle import CycleTerritoryBattle
    users, clans, _, cycle = world
    initialize(db, world)
    battle = db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle.id).one()
    sides = battle.sides
    battle.sides = [s for s in sides if s['clan_id'] == battle.owner_clan_id]
    db.flush()
    service = CycleMapService()
    def read():
        return service.read(db, cycle_id=cycle.id, actor_user_id=users[7].id, now=T)['battles'][0]
    assert read()['status'] == 'defense'
    battle.owner_clan_id = None
    battle.sides = [s for s in sides if s['clan_id'] == clans[2].id]
    db.flush()
    assert read()['status'] == 'neutral_claim'
    assert all(s['role'] == 'attacker' for s in read()['sides'])
    battle.sides = sides
    db.flush()
    assert read()['status'] == 'contested'
