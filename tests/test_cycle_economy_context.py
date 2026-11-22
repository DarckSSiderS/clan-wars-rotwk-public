from app.models.cycle_economy import CycleEconomyState
from app.models.clan import ClanMember
from tests.test_cycle_economy_api import economy_world, client_for


def test_economy_context_is_private_and_does_not_initialize(db, monkeypatch):
    users, clan, _, cycle = economy_world(db, monkeypatch)
    db.commit()
    url = f'/economy/seasons/{cycle.season_id}/clans/{clan.id}/context'
    data = client_for(db, users[0]).get(url).json()
    assert data['ready'] is False and data['can_manage']
    assert db.query(CycleEconomyState).count() == 0
    assert client_for(db, users[3]).get(url).status_code == 403


def test_context_has_three_level_prices_effects_and_role_specific_controls(db, monkeypatch):
    users, clan, land, cycle = economy_world(db, monkeypatch)
    db.query(ClanMember).filter_by(user_id=users[2].id).update({'is_trader': True})
    db.commit()
    base = f'/economy/seasons/{cycle.season_id}/clans/{clan.id}'
    client = client_for(db, users[0])
    client.post(base + '/initialize')
    data = client.get(base + '/context').json()
    assert data['ready'] and data['can_manage'] and data['can_trade']
    assert data['state']['wallet']['gold'] == '1000'
    assert len(data['catalog']) == 15
    assert len(data['catalog'][0]['costs']) == len(data['catalog'][0]['effects']) == 3
    assert data['lands'][0]['territory_id'] == land.id
    assert data['lands'][0]['quotes']['gold']['cost']['gold'] == '300'
    trader = client_for(db, users[2]).get(base + '/context').json()
    assert not trader['can_manage'] and trader['can_trade']
    assert not client_for(db, users[1]).get(base + '/context').json()['can_trade']
