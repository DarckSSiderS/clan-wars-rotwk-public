from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.clan import Clan, ClanMember
from app.models.cycle_startup import CycleStartup, CycleStartupClan, CycleStartupIdentity
from app.models.external_identity import ExternalPlayerIdentity
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.models.user import User
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.cycle_startup_service import CycleStartupService


NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


@pytest.fixture
def startup(db):
    season = CampaignSeason(number=1, name='Startup', status='active', starts_at=NOW,
                            rules_snapshot={'version': 1, 'mechanics_version': 'cycle_v1'})
    clans = [Clan(name=f'Clan {i}', leader_id=100 + i) for i in range(9)]
    db.add_all([season, *clans])
    db.flush()
    cycle = CampaignCycleStore().start(db, season_id=season.id)
    lands = [Territory(name=f'Land {i}', region='R', svg_path_data=f'path-{i}',
        is_playable=True, development_level=5, fortifications=3, offense_level=7,
        adjacent_territory_ids=[]) for i in range(30)]
    db.add_all(lands)
    db.flush()
    for i, land in enumerate(lands):
        land.adjacent_territory_ids = [lands[j].id for j in (i - 1, i + 1) if 0 <= j < len(lands)]
    db.flush()
    return CycleStartupService(), cycle, season, clans, lands


def members(db, clan, *, count=4, joined=NOW, offset=0, verified=True, source='bfmeladder'):
    result = []
    for i in range(count):
        uid = offset + i + 1
        user = User(username=f'user-{uid}')
        db.add(user)
        db.flush()
        member = ClanMember(clan_id=clan.id, user_id=user.id, joined_at=joined + timedelta(minutes=i))
        identity = ExternalPlayerIdentity(user_id=user.id, source=source,
            external_uuid=str(UUID(int=uid)), current_nickname=f'nick-{uid}',
            verification_status='verified' if verified else 'unverified', verified_at=joined if verified else None)
        db.add_all([member, identity])
        result.append((member, identity))
    db.flush()
    return result


def initialize(db, startup):
    service, cycle, _, _, _ = startup
    return service.initialize(db, cycle_id=cycle.id, now=NOW)


def claim(db, startup, index=0, ids=None, now=None, **extra):
    service, cycle, _, clans, lands = startup
    return service.claim(db, cycle_id=cycle.id, clan_id=clans[index].id, actor_id=100 + index,
        selected=ids or [t.id for t in lands[:3]], now=now or NOW + timedelta(hours=1), **extra)


def test_explicit_immutable_initializer_preserves_everything(db, startup):
    service, cycle, _, clans, lands = startup
    lands[0].owner_clan_id = clans[0].id
    db.flush()
    with pytest.raises(ValueError, match='initialization'):
        claim(db, startup)
    with pytest.raises(ValueError, match='explicit season start'):
        service.initialize(db, cycle_id=cycle.id, now=NOW + timedelta(seconds=1))
    state = initialize(db, startup)
    owners = dict(state.initial_owners)
    lands[0].owner_clan_id = None
    db.flush()
    assert service.initialize(db, cycle_id=cycle.id, now=NOW + timedelta(hours=1)).initial_owners == owners
    row = db.query(CycleStartupClan).one()
    assert row.initial_owned == [lands[0].id]
    assert lands[0].development_level == 5
    assert clans[0].gold == 500


def test_retained_starting_land_gets_history_without_changing_development(db, startup):
    _, _, _, clans, lands = startup
    lands[0].owner_clan_id = clans[0].id
    db.flush()
    initialize(db, startup)
    at = NOW + timedelta(hours=1)
    claim(db, startup, now=at)
    histories = db.query(TerritoryOwnershipHistory).filter_by(territory_id=lands[0].id).all()
    assert len(histories) == 1
    assert histories[0].clan_id == clans[0].id
    assert as_utc(histories[0].started_at) == at
    assert lands[0].development_level == 5
    claim(db, startup, now=at + timedelta(minutes=1))
    assert db.query(TerritoryOwnershipHistory).filter_by(territory_id=lands[0].id).count() == 1


def test_retention_dobor_releases_excess_once_with_history(db, startup):
    _, _, _, clans, lands = startup
    for land in [*lands[:2], lands[8]]:
        land.owner_clan_id = clans[0].id
    lands[8].has_port = True
    db.flush()
    initialize(db, startup)
    row = claim(db, startup)
    assert row.slot is None and row.status == 'claimed'
    assert [land.owner_clan_id for land in lands[:3]] == [clans[0].id] * 3
    assert lands[8].owner_clan_id is None
    count = db.query(TerritoryOwnershipHistory).count()
    assert claim(db, startup).id == row.id
    assert db.query(TerritoryOwnershipHistory).count() == count
    assert db.query(CycleStartupIdentity).count() == 0
    assert lands[0].adjacent_territory_ids == [lands[1].id]
    assert lands[0].svg_path_data == 'path-0'
    assert (lands[2].development_level, lands[2].fortifications, lands[2].offense_level) == (5, 3, 7)
    with pytest.raises(CycleConflict, match='immutable'):
        claim(db, startup, ids=[t.id for t in lands[3:6]])


def test_retention_preferred_and_fallback_when_impossible(db, startup):
    _, _, _, clans, lands = startup
    lands[0].owner_clan_id = clans[0].id
    db.flush()
    initialize(db, startup)
    with pytest.raises(ValueError, match='retain'):
        claim(db, startup, ids=[t.id for t in lands[5:8]])
    lands[1].has_port = True
    db.flush()
    claim(db, startup, ids=[t.id for t in lands[5:8]])
    assert lands[0].owner_clan_id is None


def test_all_clans_rank_by_fourth_join_not_request_order_and_limit_six(db, startup):
    service, cycle, _, clans, _ = startup
    initialize(db, startup)
    # Clan 7 requests first, but six clans actually reached four earlier.
    for index in range(7):
        members(db, clans[index], offset=index * 10, joined=NOW + timedelta(minutes=index * 5))
    with pytest.raises(ValueError, match='not eligible'):
        claim(db, startup, index=6)
    rows = service.qualify(db, cycle_id=cycle.id, now=NOW + timedelta(hours=1))
    assert [r.clan_id for r in rows] == [c.id for c in clans[:6]]
    assert [r.slot for r in rows] == list(range(1, 7))
    assert as_utc(rows[0].qualified_at) == NOW + timedelta(minutes=3)
    assert db.query(CycleStartupIdentity).count() == 24
    service.qualify(db, cycle_id=cycle.id, now=NOW + timedelta(hours=2))
    assert db.query(CycleStartupIdentity).count() == 24
    # No selection queue: sixth can pick before first.
    claim(db, startup, index=5)


def test_ties_by_clan_id_and_only_selected_four_reserved(db, startup):
    service, cycle, _, clans, _ = startup
    initialize(db, startup)
    members(db, clans[1], offset=20, count=5)
    members(db, clans[0], offset=10, count=5)
    rows = service.qualify(db, cycle_id=cycle.id, now=NOW + timedelta(hours=1))
    assert [r.clan_id for r in rows] == [clans[0].id, clans[1].id]
    assert db.query(CycleStartupIdentity).count() == 8
    assert str(UUID(int=15)) not in {r.external_uuid for r in db.query(CycleStartupIdentity).all()}


def test_verified_source_uuid_and_actual_four_members_required(db, startup):
    service, cycle, _, clans, _ = startup
    initialize(db, startup)
    a = members(db, clans[0], offset=10, verified=False)
    members(db, clans[1], offset=20, source='other')
    c = members(db, clans[2], offset=30)
    c[0][1].external_uuid = 'nickname-not-uuid'
    db.flush()
    assert service.qualify(db, cycle_id=cycle.id, now=NOW + timedelta(hours=1)) == []
    for _, identity in a:
        identity.verification_status = 'verified'
    db.flush()
    assert len(service.qualify(db, cycle_id=cycle.id, now=NOW + timedelta(hours=1))) == 1
    db.delete(a[0][0])
    db.flush()
    with pytest.raises(ValueError, match='remain current verified'):
        claim(db, startup)
    # A qualification is not released/reassigned when selected membership drops.
    assert db.query(CycleStartupIdentity).count() == 4
    assert db.query(CycleStartupClan).one().slot == 1


def test_used_uuid_cannot_qualify_another_clan_but_unselected_can(db, startup):
    service, cycle, _, clans, _ = startup
    initialize(db, startup)
    original = members(db, clans[0], offset=10, count=5)
    service.qualify(db, cycle_id=cycle.id, now=NOW + timedelta(hours=1))
    for member, _ in original:
        member.clan_id = clans[1].id
    db.flush()
    assert len(service.qualify(db, cycle_id=cycle.id, now=NOW + timedelta(hours=2))) == 1
    members(db, clans[1], offset=40, count=3, joined=NOW + timedelta(hours=2))
    rows = service.qualify(db, cycle_id=cycle.id, now=NOW + timedelta(hours=3))
    assert len(rows) == 2
    assert str(UUID(int=15)) in [m['uuid'] for m in rows[1].selected_four]


def test_competing_claims_stale_revision_and_atomic_rollback(db, startup, monkeypatch):
    service, cycle, _, clans, lands = startup
    initialize(db, startup)
    for i in range(2):
        members(db, clans[i], offset=10 * i)
    service.qualify(db, cycle_id=cycle.id, now=NOW + timedelta(hours=1))
    with pytest.raises(CycleConflict):
        claim(db, startup, expected_revision=0)
    transfer = service._transfer
    calls = []

    def fail_second(*args):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError('injected failure')
        return transfer(*args)

    monkeypatch.setattr(service, '_transfer', fail_second)
    with pytest.raises(RuntimeError):
        claim(db, startup)
    assert all(t.owner_clan_id is None for t in lands)
    assert db.query(TerritoryOwnershipHistory).count() == 0
    monkeypatch.setattr(service, '_transfer', transfer)
    claim(db, startup)
    with pytest.raises(ValueError, match='available'):
        claim(db, startup, index=1)
    assert db.query(CycleStartupClan).filter_by(clan_id=clans[1].id).one().status == 'pending'
    assert db.query(TerritoryOwnershipHistory).count() == 3


def test_preview_has_no_receipts_or_transfers(db, startup):
    service, cycle, _, clans, lands = startup
    initialize(db, startup)
    members(db, clans[0], offset=10)
    preview = service.preview(db, cycle_id=cycle.id, clan_id=clans[0].id, actor_id=100,
        selected=[t.id for t in lands[:3]], now=NOW + timedelta(hours=1))
    assert preview['basis'] == 'gift' and preview['slot'] == 1
    assert db.query(CycleStartupClan).count() == 0
    assert db.query(CycleStartupIdentity).count() == 0
    assert db.query(TerritoryOwnershipHistory).count() == 0
    assert all(t.owner_clan_id is None for t in lands)


def test_deadline_neutralizes_initial_lands_no_gift_or_recycling(db, startup):
    service, cycle, _, clans, lands = startup
    lands[8].owner_clan_id = clans[0].id
    lands[9].owner_clan_id = clans[1].id
    db.flush()
    state = initialize(db, startup)
    members(db, clans[2], offset=10)
    claim(db, startup, index=2)
    deadline = as_utc(state.deadline)
    with pytest.raises(ValueError, match='deadline'):
        claim(db, startup, ids=[t.id for t in lands[6:9]], now=deadline)
    with pytest.raises(ValueError, match='not arrived'):
        service.expire(db, cycle_id=cycle.id, now=deadline - timedelta(microseconds=1))
    service.expire(db, cycle_id=cycle.id, now=deadline)
    assert lands[8].owner_clan_id is None and lands[9].owner_clan_id is None
    assert all(t.owner_clan_id == clans[2].id for t in lands[:3])
    assert lands[8].development_level == 5
    count = db.query(TerritoryOwnershipHistory).count()
    service.expire(db, cycle_id=cycle.id, now=deadline + timedelta(hours=1))
    assert db.query(TerritoryOwnershipHistory).count() == count
    members(db, clans[3], offset=30, joined=deadline)
    with pytest.raises(ValueError, match='deadline'):
        claim(db, startup, index=3, now=deadline + timedelta(hours=1))
    assert db.query(CycleStartupIdentity).count() == 4


@pytest.mark.parametrize('kind', ['port', 'fortress', 'disconnected', 'enemy', 'unplayable'])
def test_illegal_starting_triples(db, startup, kind):
    _, _, _, clans, lands = startup
    members(db, clans[0], offset=10)
    initialize(db, startup)
    ids = [t.id for t in lands[:3]]
    if kind == 'port':
        lands[1].has_port = True
    elif kind == 'fortress':
        lands[1].stronghold_power = 1
    elif kind == 'disconnected':
        ids[-1] = lands[9].id
    elif kind == 'enemy':
        lands[1].owner_clan_id = clans[1].id
    else:
        lands[1].is_playable = False
    db.flush()
    with pytest.raises(ValueError):
        claim(db, startup, ids=ids)
    assert not db.query(CycleStartupClan).filter_by(status='claimed').count()


def test_only_head_old_season_and_caller_rollback(db, startup):
    service, cycle, season, clans, _ = startup
    initialize(db, startup)
    members(db, clans[0], offset=10)
    with pytest.raises(PermissionError):
        service.claim(db, cycle_id=cycle.id, clan_id=clans[0].id, actor_id=999,
                      selected=[1, 2, 3], now=NOW + timedelta(hours=1))
    season.rules_snapshot = {'mechanics_version': 'legacy'}
    db.flush()
    with pytest.raises(ValueError, match='cycle_v1'):
        claim(db, startup)
    season.rules_snapshot = {'version': 1, 'mechanics_version': 'cycle_v1'}
    db.flush()
    claim(db, startup)
    db.rollback()
    assert db.query(CycleStartup).count() == 0
    assert db.query(TerritoryOwnershipHistory).count() == 0
