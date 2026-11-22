from app.models.campaign_cycle import CycleScoutRequest
from app.models.cycle_economy import CycleEconomyState
from tests.test_cycle_operations_api import client_for, path
from tests.test_cycle_plan_service import setup_world
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_economy_store import CycleEconomyStore


def test_preparation_context_private_and_no_initializer(db, monkeypatch):
    users, clan, _, cycle = setup_world(db)
    now = CampaignCycleStore.timeline(cycle).preparation_at
    db.commit()
    client, _ = client_for(db, monkeypatch, users[1], now)
    url = path(cycle, clan) + '/preparation'
    result = client.get(url)
    assert result.status_code == 200
    assert not result.json()['scout']['can_request']
    assert not result.json()['startup']['ready']
    assert db.query(CycleEconomyState).count() == 0
    other, _ = client_for(db, monkeypatch, users[3], now)
    assert other.get(url).status_code == 403


def test_voivode_can_scout_but_members_cannot(db, monkeypatch):
    users, clan, land, cycle = setup_world(db)
    CycleEconomyStore().ensure_state(db, season_id=cycle.season_id, clan_id=clan.id)
    now = CampaignCycleStore.timeline(cycle).preparation_at
    db.commit()
    client, _ = client_for(db, monkeypatch, users[1], now)
    url = path(cycle, clan) + '/preparation'
    data = client.get(url).json()
    assert data['scout']['can_request']
    assert data['scout']['price'] == '200'
    member, _ = client_for(db, monkeypatch, users[2], now)
    assert not member.get(url).json()['scout']['can_request']
    row = CycleScoutRequest(cycle_id=cycle.id, clan_id=clan.id, territory_id=land.id,
                           actor_user_id=users[1].id, requested_at=now)
    db.add(row); db.commit()
    after = client.get(url).json()
    assert not after['scout']['can_request']
    assert after['scout']['request']['territory_id'] == land.id


def test_retained_startup_context_preview_and_claim_real_services(db, monkeypatch):
    from datetime import timedelta
    from app.models.territory import Territory
    from app.services.cycle_startup_service import CycleStartupService
    from tests.test_campaign_cycle_store import START
    users, clan, land, cycle = setup_world(db)
    neighbours = [Territory(name=f'Start {i}', region='Test', svg_path_data='M0 0', is_playable=True) for i in range(2)]
    db.add_all(neighbours); db.flush()
    land.adjacent_territory_ids = [neighbours[0].id]
    neighbours[0].adjacent_territory_ids = [land.id, neighbours[1].id]
    neighbours[1].adjacent_territory_ids = [neighbours[0].id]
    CycleStartupService().initialize(db, cycle_id=cycle.id, now=START)
    db.commit()
    locked = []
    original_lock = CampaignCycleStore._locked
    def lock(self, db, cycle_id, expected_revision=None):
        locked.append(cycle_id)
        return original_lock(self, db, cycle_id, expected_revision)
    monkeypatch.setattr(CampaignCycleStore, '_locked', lock)
    original_projection = CycleStartupService._projection
    def projection(self, db, startup, now):
        assert locked, 'Preparation projection must lock the cycle before startup/clan rows'
        return original_projection(self, db, startup, now)
    monkeypatch.setattr(CycleStartupService, '_projection', projection)
    client, _ = client_for(db, monkeypatch, users[0], START + timedelta(hours=1))
    base = path(cycle, clan)
    before = client.get(base + '/preparation').json()
    assert before['startup']['can_claim'] and before['startup']['initial_owned'] == [land.id]
    chosen = [land.id, *[t.id for t in neighbours]]
    preview = client.post(base + '/startup/preview', json={'selected': chosen})
    assert preview.status_code == 200, preview.text
    assert preview.json()['release'] == []
    confirmed = client.post(base + '/startup/claim', json={'selected': chosen, 'expected_revision': before['startup']['revision']})
    assert confirmed.status_code == 200, confirmed.text
    assert not client.get(base + '/preparation').json()['startup']['can_claim']
