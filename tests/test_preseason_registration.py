import importlib
from datetime import timedelta

import pytest

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.clan import Clan, ClanMember
from app.models.cycle_economy import CycleEconomyState
from app.models.territory import Territory
from app.models.user import User
from app.models.season_archive import CampaignSeasonArchive
from app.services.season_archive_service import SeasonArchiveService
from tests.test_cycle_season_launch import world as launch_world, NOW


def service():
    try:
        return importlib.import_module('app.services.preseason_service').PreseasonService()
    except ModuleNotFoundError:
        pytest.fail('Нет регистрации до ручного запуска сезона')


@pytest.fixture
def world(db, launch_world):
    season = db.get(CampaignSeason, 1)
    season.ends_at = NOW
    user = db.get(User, 1)
    user.onboarding_completed_at = NOW
    user.is_claimed = True
    lands = [db.query(Territory).filter_by(name=name).one() for name in ('Шир', 'Эвендим', 'Арнор')]
    for land in lands:
        land.adjacent_territory_ids = [other.id for other in lands if other.id != land.id]
    db.flush()
    archive = SeasonArchiveService().capture(db, season)
    db.commit()
    return launch_world, [land.id for land in lands], archive.checksum


def opened(db, world):
    service().open(db, actor_user_id=1, now=NOW + timedelta(days=1))
    db.commit()
    return service()


def test_open_clears_real_ownership_but_preserves_archive_and_rights(db, world):
    clan_id, lands, checksum = world
    opened(db, world)
    assert db.query(Territory).filter(Territory.owner_clan_id.isnot(None)).count() == 0
    assert db.get(Clan, clan_id).territory_points == 0
    context = service().read(db, clan_id=clan_id, actor_id=1, now=NOW + timedelta(days=1))
    assert context['initial_owned'] == [lands[0]]
    assert context['open'] and context['can_choose_lands'] and context['can_choose_relics']
    assert 'deadline' not in context
    assert db.get(CampaignSeasonArchive, 1).checksum == checksum
    assert db.query(CampaignSeason).count() == 1
    assert db.query(CampaignCycleRecord).count() == db.query(CycleEconomyState).count() == 0


def test_read_and_preview_do_not_reserve_or_write_and_time_does_not_expire(db, world):
    clan_id, lands, _ = world
    s = opened(db, world)
    now = NOW + timedelta(days=400)
    result = s.read(db, clan_id=clan_id, actor_id=1, now=now)
    assert result['can_choose_lands']
    assert next(t for t in result['territories'] if t['id'] == lands[0])['selection_owner_clan_id'] == clan_id
    preview = s.preview(db, clan_id=clan_id, actor_id=1, selected=lands, now=now)
    assert preview['selected'] == sorted(lands)
    assert not db.dirty and not db.new
    assert db.query(Territory).filter(Territory.owner_clan_id.isnot(None)).count() == 0


def test_head_claims_three_and_two_relics_once_without_spending_or_income(db, world):
    clan_id, lands, checksum = world
    s = opened(db, world)
    now = NOW + timedelta(days=2)
    value = s.claim_lands(db, clan_id=clan_id, actor_id=1, selected=lands, expected_revision=1, now=now)
    assert value['selected_lands'] == sorted(lands) and value['revision'] == 2
    assert s.claim_lands(db, clan_id=clan_id, actor_id=1, selected=lands, expected_revision=1, now=now) == value
    value = s.claim_relics(db, clan_id=clan_id, actor_id=1, selected=['royal_charter', 'white_tree'], expected_revision=2, now=now)
    assert set(value['selected_relics']) == {'royal_charter', 'white_tree'}
    assert db.query(Territory).filter_by(owner_clan_id=clan_id).count() == 3
    assert db.get(Clan, clan_id).gold == 9876
    assert db.query(CycleEconomyState).count() == 0
    assert db.get(CampaignSeasonArchive, 1).checksum == checksum
    with pytest.raises(ValueError):
        s.claim_relics(db, clan_id=clan_id, actor_id=1, selected=['royal_charter', 'war_foundry'], expected_revision=3, now=now)


def test_member_and_voivode_cannot_claim_for_the_head(db, world):
    clan_id, lands, _ = world
    db.add(User(id=2, username='Воевода', is_active=True, onboarding_completed_at=NOW))
    db.add(ClanMember(user_id=2, clan_id=clan_id, rank='Воин', is_warlord=True, joined_at=NOW))
    db.commit()
    s = opened(db, world)
    context = s.read(db, clan_id=clan_id, actor_id=2, now=NOW + timedelta(days=1))
    assert not context['can_choose_lands'] and not context['can_choose_relics']
    with pytest.raises(PermissionError):
        s.claim_lands(db, clan_id=clan_id, actor_id=2, selected=lands, expected_revision=1, now=NOW)
    with pytest.raises(PermissionError):
        s.read(db, clan_id=clan_id, actor_id=999, now=NOW)


def test_manual_launch_imports_choices_without_duplicate_gifts(db, world):
    from app.services.cycle_season_launch_service import CycleSeasonLaunchService
    from app.models.cycle_startup import CycleStartupClan
    clan_id, lands, _ = world
    s = opened(db, world)
    s.claim_lands(db, clan_id=clan_id, actor_id=1, selected=lands, expected_revision=1, now=NOW + timedelta(days=1))
    s.claim_relics(db, clan_id=clan_id, actor_id=1, selected=['royal_charter', 'white_tree'], expected_revision=2, now=NOW + timedelta(days=1))
    db.commit()
    result = CycleSeasonLaunchService().start(db, actor_user_id=1, name='Сезон 2', command_id='manual', previous_season_id=1, now=NOW + timedelta(days=9))
    state = db.query(CycleEconomyState).filter_by(season_id=result['season_id'], clan_id=clan_id).one()
    assert state.starters_chosen and state.relics == {'royal_charter': 1, 'white_tree': 1}
    assert state.wallet['gold'] == '1000'
    claim = db.query(CycleStartupClan).filter_by(season_id=result['season_id'], clan_id=clan_id).one()
    assert claim.status == 'claimed' and claim.initial_owned == [lands[0]]
    assert claim.selected_lands == sorted(lands)
    assert not service().status(db)['open']


def test_pending_rights_survive_launch_without_restoring_old_map_ownership(db, world):
    from app.services.cycle_season_launch_service import CycleSeasonLaunchService
    from app.services.cycle_startup_service import CycleStartupService
    clan_id, lands, _ = world
    opened(db, world)
    result = CycleSeasonLaunchService().start(db, actor_user_id=1, name='Новый', command_id='pending', previous_season_id=1, now=NOW + timedelta(days=2))
    assert db.query(Territory).filter(Territory.owner_clan_id.isnot(None)).count() == 0
    CycleStartupService().claim(db, cycle_id=result['cycle_id'], clan_id=clan_id, actor_id=1,
                               selected=lands, now=NOW + timedelta(days=2, hours=1))
    assert db.query(Territory).filter_by(owner_clan_id=clan_id).count() == 3
    assert db.get(Clan, clan_id).territory_points == 150


def test_http_status_is_public_but_choices_are_private_and_head_only(db, world):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.v1.campaign import router
    from app.database import get_db
    from app.core.auth import get_current_active_user, get_onboarded_active_user
    site = FastAPI()
    site.include_router(router)
    site.dependency_overrides[get_db] = lambda: db
    client = TestClient(site)
    prefix = '/campaign/preseason'
    assert client.get(prefix + '/status').json() == {'open': False, 'preparation_id': None}
    opened(db, world)
    assert client.get(prefix + '/status').json()['open']
    assert client.get(prefix + '/clans/1').status_code == 401
    assert client.post(prefix + '/clans/1/lands', json={'selected': world[1], 'expected_revision': 1}).status_code == 401
    site.dependency_overrides[get_current_active_user] = lambda: db.get(User, 1)
    site.dependency_overrides[get_onboarded_active_user] = lambda: db.get(User, 1)
    assert client.get(prefix + '/clans/1').json()['can_choose_lands']
    assert client.post(prefix + '/clans/1/lands/preview', json={'selected': world[1]}).status_code == 200
    assert client.post(prefix + '/clans/1/lands', json={'selected': world[1], 'expected_revision': 1}).status_code == 200
    assert client.post(prefix + '/clans/1/relics', json={'selected': ['royal_charter', 'white_tree'], 'expected_revision': 1}).status_code == 409


def test_join_hook_keeps_first_six_uuid_receipts_without_a_browser_request(db, world):
    from uuid import UUID
    from app.models.external_identity import ExternalPlayerIdentity
    from app.models.preseason import CampaignPreseason
    from app.services.clan_membership_service import ClanMembershipService
    opened(db, world)
    db.add(Clan(id=2, name='Новички', leader_id=2, is_deleted=False, is_admin_clan=False))
    for i in range(2, 6):
        db.add(User(id=i, username=f'Новый{i}', is_active=True, onboarding_completed_at=NOW))
        db.add(ExternalPlayerIdentity(user_id=i, source='bfmeladder', external_uuid=str(UUID(int=i)), current_nickname=f'Новый{i}', current_nickname_key=f'новый{i}', verification_status='verified', verified_at=NOW))
    db.commit()
    for i in range(2, 6):
        member = ClanMember(user_id=i, clan_id=2, rank='Воин', joined_at=NOW)
        db.add(member)
        db.commit()
        ClanMembershipService().start(db, member, started_at=NOW)
    receipt = db.get(CampaignPreseason, 1).qualifications.get('2')
    assert receipt and receipt['slot'] == 1 and len(receipt['selected_four']) == 4
    db.query(ClanMember).filter_by(user_id=5).delete()
    db.commit()
    assert not service().read(db, clan_id=2, actor_id=2, now=NOW + timedelta(days=2))['can_choose_lands']
    assert db.get(CampaignPreseason, 1).qualifications['2'] == receipt


def test_purged_clan_does_not_reserve_lands_but_keeps_consumed_gift_slots(db, world):
    from app.models.preseason import CampaignPreseason
    from app.models.cycle_startup import CycleStartup
    from app.services.cycle_season_launch_service import CycleSeasonLaunchService
    from app.services.cycle_startup_service import CycleStartupService
    opened(db, world)
    parent = db.get(CampaignPreseason, 1)
    parent.initial_owners = {str(i): 999 for i in world[1]}
    parent.qualifications = {'999': {'slot': 1, 'qualified_at': NOW.isoformat(), 'selected_four': [
        {'user_id': i, 'source': 'bfmeladder', 'uuid': f'00000000-0000-0000-0000-{i:012d}', 'joined_at': NOW.isoformat()} for i in range(4)]}}
    db.commit()
    assert all(t['selection_owner_clan_id'] is None for t in service().read(db, clan_id=1, actor_id=1, now=NOW)['territories'])
    report = CycleSeasonLaunchService().start(db, actor_user_id=1, name='Новый', command_id='purged', previous_season_id=1, now=NOW+timedelta(days=2))
    season = db.get(CampaignSeason, report['season_id'])
    startup = db.get(CycleStartup, season.id)
    lands = db.query(Territory).all()
    assert all(t.owner_clan_id is None for t in CycleStartupService().selection_world(db, season, startup, lands, {}))


def test_invalid_lands_explain_the_problem_in_russian(db, world):
    opened(db, world)
    with pytest.raises(ValueError, match='три разные'):
        service().preview(db, clan_id=1, actor_id=1, selected=[world[1][0]]*3, now=NOW)


def test_open_closes_stale_history_even_if_live_land_was_already_neutral(db, world):
    from app.models.territory import TerritoryOwnershipHistory
    history=TerritoryOwnershipHistory(territory_id=world[1][1],clan_id=1,started_at=NOW-timedelta(days=3),reason='legacy')
    db.add(history)
    db.commit()
    opened(db, world)
    assert as_utc(history.ended_at)==NOW+timedelta(days=1)


def pending_four(db):
    from uuid import UUID
    from app.models.external_identity import ExternalPlayerIdentity
    for i in range(2,6):
        db.add(User(id=i,username=f'Игрок{i}',is_active=True,is_claimed=True,onboarding_completed_at=NOW))
    db.flush()
    db.add(Clan(id=2,name='Новый',leader_id=2,is_deleted=False,is_admin_clan=False))
    db.flush()
    for i in range(2,6):
        db.add(ExternalPlayerIdentity(user_id=i,source='bfmeladder',external_uuid=str(UUID(int=i)),current_nickname=f'Игрок{i}',current_nickname_key=f'игрок{i}',verification_status='pending'))
        db.add(ClanMember(user_id=i,clan_id=2,rank='Воин',joined_at=NOW))
    db.commit()


def test_verification_of_fourth_uuid_durably_allocates_slot_without_get(db,world):
    from app.models.preseason import CampaignPreseason
    from app.services.external_identity_service import ExternalIdentityService
    opened(db,world)
    pending_four(db)
    for i in range(2,6):
        ExternalIdentityService().review_verification(db,target_user=db.get(User,i),reviewer=db.get(User,1),decision='approve',reason='Подтверждение')
    receipt=db.get(CampaignPreseason,1).qualifications.get('2')
    assert receipt and receipt['slot']==1


def test_join_snapshot_survives_leave_between_commit_and_qualification(db,world,monkeypatch):
    from app.models.preseason import CampaignPreseason
    from app.models.external_identity import ExternalPlayerIdentity
    from app.services.clan_service import ClanService
    from app.core.time import utc_now
    opened(db,world)
    pending_four(db)
    for identity in db.query(ExternalPlayerIdentity).filter(ExternalPlayerIdentity.user_id.in_(range(2,6))):
        identity.verification_status='verified'
        identity.verified_at=NOW
    db.query(ClanMember).filter_by(user_id=5).delete()
    db.commit()
    monkeypatch.setattr(service().__class__,'qualify_open',lambda *args,**kwargs:False)
    ClanService()._create_member(db,dict(user_id=5,clan_id=2,rank='Воин',joined_at=NOW),reason='joined')
    # Имитируем выход, пока распределение квитанций ещё не выполнилось.
    db.query(ClanMember).filter_by(user_id=5).delete()
    db.commit()
    service()._qualifications(db,db.get(CampaignPreseason,1),utc_now(),persist=True)
    db.commit()
    receipt=db.get(CampaignPreseason,1).qualifications.get('2')
    assert receipt and receipt['slot']==1 and len(receipt['selected_four'])==4
    assert not service().read(db,clan_id=2,actor_id=2,now=utc_now())['can_choose_lands']
