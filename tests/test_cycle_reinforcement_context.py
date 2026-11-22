from datetime import timedelta

import pytest

from app.models.campaign import CampaignSeason
from app.models.clan import ClanMember
from app.models.cycle_reinforcement_state import CycleReinforcementState
from app.models.external_identity import ExternalPlayerIdentity
from app.services.cycle_reinforcement_store import CycleReinforcementStore
from tests.test_cycle_reinforcement_store import world, initialize, request, send, T
from tests.test_cycle_operations_api import client_for, path


def context(db, world, *, clan=0, actor=None, now=T):
    users, clans, _, cycle = world
    return CycleReinforcementStore().context(db, cycle_id=cycle.id, viewer_clan_id=clans[clan].id,
                                            actor_user_id=actor or clans[clan].leader_id, now=now)


def test_context_before_initialization_is_read_only_and_has_no_side_effects(db, world):
    data = context(db, world)
    assert not data['ready'] and not data['can_command']
    assert data['state'] is None and data['players'] == []
    assert db.query(CycleReinforcementState).count() == 0


def test_context_private_roster_roles_and_permanent_ids(db, world):
    users, clans, _, _ = world
    initialize(db, world)
    data = context(db, world)
    assert data['can_command'] and data['ready']
    assert [p['user_id'] for p in data['players']] == [users[1].id, users[2].id]
    assert all(p['available'] for p in data['players'])
    assert data['command_deadline'] == T + timedelta(hours=24)
    assert context(db, world, actor=users[2].id)['can_command']
    assert not context(db, world, actor=users[1].id)['can_command']
    assert 'uuid' not in str(data) and 'bindings' not in data and 'reserve_history' not in data
    users[1].username = 'Renamed reserve'
    db.flush()
    assert context(db, world)['players'][0]['name'] == 'Renamed reserve'
    with pytest.raises(PermissionError):
        context(db, world, actor=users[3].id)


def test_open_allied_request_disappears_after_first_dispatch_and_can_be_reopened(db, world):
    users, clans, land, _ = world
    initialize(db, world)
    recipient = context(db, world, clan=1)
    assert recipient['help_targets'] == [land.id]
    request(db, world)
    data = context(db, world)
    assert data['allied_targets'][0]['request_id'] == 'q'
    assert data['allied_targets'][0]['recipient_clan_id'] == clans[1].id
    assert context(db, world, clan=1)['help_targets'] == []
    send(db, world)
    after = context(db, world)
    assert after['allied_targets'] == []
    assert next(p for p in after['players'] if p['user_id'] == users[1].id)['unavailable_reason'] == 'already_sent'
    assert context(db, world, clan=1)['help_targets'] == [land.id]
    request(db, world, command='q2')
    assert context(db, world)['allied_targets'][0]['request_id'] == 'q2'


def test_ineligible_or_rebound_reservist_is_visible_but_not_selectable(db, world):
    users, _, _, _ = world
    initialize(db, world)
    db.query(ClanMember).filter_by(user_id=users[1].id).delete()
    identity = db.query(ExternalPlayerIdentity).filter_by(user_id=users[2].id).one()
    identity.external_uuid = '00000000-0000-0000-0000-000000000099'
    db.flush()
    data = context(db, world)
    assert len(data['players']) == 2 and not any(p['available'] for p in data['players'])


@pytest.mark.parametrize('offset', [-1, 86400, 172800])
def test_context_command_window_uses_server_time(db, world, offset):
    initialize(db, world)
    assert not context(db, world, now=T + timedelta(seconds=offset))['can_command']


def test_archived_season_cannot_create_new_help_or_dispatch(db, world):
    _, _, _, cycle = world
    initialize(db, world)
    request(db, world)
    db.get(CampaignSeason, cycle.season_id).status = 'completed'
    db.flush()
    assert not context(db, world)['can_command']
    with pytest.raises(ValueError, match='active'):
        request(db, world, command='new-request')
    with pytest.raises(ValueError, match='active'):
        send(db, world)


def test_context_api_authentication_and_membership(db, world, monkeypatch):
    users, clans, _, cycle = world
    initialize(db, world)
    db.commit()
    client, app = client_for(db, monkeypatch, users[0], T)
    url = path(cycle, clans[0]) + '/reinforcements/context'
    assert client.get(url).json()['ready'] is True
    from app.core.auth import get_current_active_user
    app.dependency_overrides[get_current_active_user] = lambda: users[7]
    assert client.get(url).status_code == 403


def test_context_never_discloses_untriggered_foreign_ambush_players(db, world):
    users, clans, _, _ = world
    initialize(db, world)
    before = context(db, world)
    assert before['state']['ambushes'] == []
    assert users[6].id not in {p['user_id'] for p in before['names']}
    assert clans[2].id not in {c['id'] for c in before['clans']}
    request(db, world)
    send(db, world)
    after = context(db, world)
    assert after['state']['ambushes'][0]['clan_id'] == clans[2].id
    assert users[6].id in {p['user_id'] for p in after['names']}
    assert after['state']['dispatches'][0]['interception_at'] == T + timedelta(hours=2)
    assert after['state']['dispatches'][0]['interception_ends_at'] == T + timedelta(hours=14)


def test_allied_request_target_requires_no_conflicting_ordinary_side(db, world):
    from app.models.campaign_cycle import CampaignCyclePlan
    from app.models.cycle_battle import CycleTerritoryBattle
    from app.services.cycle_battle_service import CycleBattleService
    users, clans, land, cycle = world
    plan = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id, clan_id=clans[0].id).one()
    plan.orders = [*plan.orders, {'user_id': users[0].id, 'kind': 'attack', 'territory_id': land.id}]
    db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle.id).delete()
    cycle.battles_registered = False
    db.flush()
    CycleBattleService().create_from_orders(db, cycle_id=cycle.id)
    initialize(db, world)
    request(db, world)
    data = context(db, world)
    assert data['allied_targets'] == []
    assert data['own_targets'][0]['territory_id'] == land.id
