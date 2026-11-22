from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.cycle_diplomacy import router
from app.core.auth import get_current_active_user
from app.database import get_db
from app.models.clan import Clan, ClanMember
from app.services.campaign_cycle_store import CampaignCycleStore
from tests.test_cycle_plan_service import setup_world


def test_private_proposals_and_head_only_war_commands(db, monkeypatch):
    users, clan, _, cycle = setup_world(db)
    other = Clan(name='Neighbour', leader_id=users[3].id)
    db.add(other)
    db.flush()
    db.add(ClanMember(user_id=users[3].id, clan_id=other.id))
    db.flush()
    monkeypatch.setattr('app.api.v1.cycle_diplomacy.utc_now', lambda: CampaignCycleStore.timeline(cycle).preparation_at)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: users[0]
    client = TestClient(app)
    url = f'/diplomacy/cycles/{cycle.id}'
    own_url = f'{url}/clans/{clan.id}'
    response = client.post(own_url, json={'action': 'offer_alliance', 'other_clan_id': other.id})
    assert response.status_code == 200
    assert client.get(url).json()['relations'] == []
    assert client.get(own_url).json()['proposals'][0]['kind'] == 'alliance'
    app.dependency_overrides[get_current_active_user] = lambda: users[3]
    assert client.get(own_url).status_code == 403
    app.dependency_overrides[get_current_active_user] = lambda: users[1]
    assert client.post(own_url, json={'action': 'declare_war', 'other_clan_id': other.id, 'duration': 2}).status_code == 403
