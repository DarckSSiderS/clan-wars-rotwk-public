from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from sqlalchemy.orm import Session

from app.models.campaign import CampaignSeason
from app.models.clan import Clan
from app.models.user import User
from app.models.territory import Territory
from app.models.preseason import CampaignPreseasonChoice
from app.models.cycle_startup import CycleStartupClan
from app.services.preseason_service import PreseasonService
from app.services.season_archive_service import SeasonArchiveService
from app.services.cycle_season_launch_service import CycleSeasonLaunchService
from app.services.campaign_rule_service import CampaignRuleService
from tests.test_cycle_launch_preflight import seed, NOW


def setup(db):
    seed(db)
    CampaignRuleService().get_active(db)
    db.add(User(id=1, username='Администратор', role_id=1, is_active=True, onboarding_completed_at=NOW, is_claimed=True))
    db.flush()
    db.add(Clan(id=1, name='Первый', leader_id=1))
    db.flush()
    lands = [db.query(Territory).filter_by(name=n).one() for n in ('Шир','Арнор','Эвендим')]
    for land in lands:
        land.adjacent_territory_ids = [other.id for other in lands if other.id != land.id]
    lands[0].owner_clan_id = 1
    season = db.get(CampaignSeason, 1)
    season.ends_at = NOW
    db.flush()
    SeasonArchiveService().capture(db, season)
    db.commit()
    PreseasonService().open(db,actor_user_id=1,now=NOW+timedelta(days=1))
    db.commit()
    return [t.id for t in lands]


def test_postgres_preseason_revision_serializes_simultaneous_land_and_relic_choices(postgres_db):
    db=postgres_db
    lands=setup(db)
    barrier=Barrier(2)
    def choose(kind):
        with Session(db.bind) as session:
            # Прогретая identity map не должна скрыть новую ревизию после ожидания lock.
            PreseasonService().read(session,clan_id=1,actor_id=1,now=NOW+timedelta(days=1))
            barrier.wait(timeout=10)
            try:
                action=PreseasonService().claim_lands if kind=='lands' else PreseasonService().claim_relics
                value=action(session,clan_id=1,actor_id=1,selected=lands if kind=='lands' else ['royal_charter','white_tree'],expected_revision=1,now=NOW+timedelta(days=1))
                session.commit()
                return value
            except ValueError:
                session.rollback()
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(choose,['lands','relics']))
    assert sum(value is not None for value in results)==1
    db.expire_all()
    assert db.query(CampaignPreseasonChoice).one().revision==2
    assert db.query(CampaignSeason).count()==1


def test_postgres_manual_launch_racing_a_claim_never_loses_confirmed_choice(postgres_db):
    db=postgres_db
    lands=setup(db)
    barrier=Barrier(2)
    def action(kind):
        with Session(db.bind) as session:
            barrier.wait(timeout=10)
            try:
                if kind=='claim':
                    value=PreseasonService().claim_lands(session,clan_id=1,actor_id=1,selected=lands,expected_revision=1,now=NOW+timedelta(days=1))
                else:
                    value=CycleSeasonLaunchService().start(session,actor_user_id=1,name='Новый',command_id='parallel',previous_season_id=1,now=NOW+timedelta(days=2))
                session.commit()
                return value
            except ValueError:
                session.rollback()
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed,launched=list(pool.map(action,['claim','launch']))
    assert launched is not None
    db.expire_all()
    receipt=db.query(CycleStartupClan).filter_by(season_id=launched['season_id'],clan_id=1).one()
    assert receipt.status==('claimed' if claimed else 'pending')
    if claimed:
        assert receipt.selected_lands==sorted(lands)
        assert db.query(Territory).filter_by(owner_clan_id=1).count()==3


def test_postgres_committed_four_snapshot_survives_another_sessions_leave(postgres_db,monkeypatch):
    from uuid import UUID
    from app.models.clan import ClanMember
    from app.models.external_identity import ExternalPlayerIdentity
    from app.models.preseason import CampaignPreseason
    from app.services.clan_service import ClanService
    from app.core.time import utc_now
    db=postgres_db
    setup(db)
    db.add_all([User(id=i,username=f'Новый{i}',is_active=True,is_claimed=True,onboarding_completed_at=NOW) for i in range(2,6)])
    db.flush()
    db.add(Clan(id=2,name='Второй',leader_id=2))
    db.flush()
    for i in range(2,6):
        db.add(ExternalPlayerIdentity(user_id=i,source='bfmeladder',external_uuid=str(UUID(int=i)),current_nickname=f'Новый{i}',current_nickname_key=f'новый{i}',verification_status='verified',verified_at=NOW))
        if i<5:db.add(ClanMember(user_id=i,clan_id=2,rank='Воин',joined_at=NOW))
    db.commit()
    monkeypatch.setattr(PreseasonService,'qualify_open',lambda *args,**kwargs:False)
    with Session(db.bind) as joining:
        ClanService()._create_member(joining,dict(user_id=5,clan_id=2,rank='Воин',joined_at=NOW),reason='joined')
    with Session(db.bind) as leaving:
        leaving.query(ClanMember).filter_by(user_id=5).delete()
        leaving.commit()
    PreseasonService()._qualifications(db,db.get(CampaignPreseason,1),utc_now(),persist=True)
    db.commit()
    assert db.get(CampaignPreseason,1).qualifications['2']['slot']==1
    assert not PreseasonService().read(db,clan_id=2,actor_id=2,now=utc_now())['can_choose_lands']


def test_postgres_parallel_third_and_fourth_join_leave_a_durable_four(postgres_db,monkeypatch):
    from threading import Event
    from uuid import UUID
    from app.models.clan import ClanMember
    from app.models.external_identity import ExternalPlayerIdentity
    from app.models.preseason import CampaignPreseason
    from app.services.clan_service import ClanService
    from app.core.time import utc_now
    db=postgres_db
    setup(db)
    db.add_all([User(id=i,username=f'Параллельный{i}',is_active=True,is_claimed=True,onboarding_completed_at=NOW) for i in range(2,6)])
    db.flush()
    db.add(Clan(id=2,name='Четвёрка',leader_id=2))
    db.flush()
    for i in range(2,6):
        db.add(ExternalPlayerIdentity(user_id=i,source='bfmeladder',external_uuid=str(UUID(int=i)),current_nickname=f'Игрок{i}',current_nickname_key=f'игрок{i}',verification_status='verified',verified_at=NOW))
        if i<4:db.add(ClanMember(user_id=i,clan_id=2,rank='Воин',joined_at=NOW))
    db.commit()
    captured,release,second_done=Event(),Event(),Event()
    original=PreseasonService.capture_candidates
    def paused(self,session,*,now):
        original(self,session,now=now)
        if session.info.get('first_join'):
            captured.set()
            assert release.wait(timeout=10)
    monkeypatch.setattr(PreseasonService,'capture_candidates',paused)
    monkeypatch.setattr(PreseasonService,'qualify_open',lambda *args,**kwargs:False)
    def join(user_id):
        with Session(db.bind) as session:
            session.info['first_join']=user_id==4
            ClanService()._create_member(session,dict(user_id=user_id,clan_id=2,rank='Воин',joined_at=NOW),reason='joined')
            if user_id==5:second_done.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(join,4)
        assert captured.wait(timeout=10)
        second=pool.submit(join,5)
        second_done.wait(timeout=1)
        release.set()
        first.result(timeout=15)
        second.result(timeout=15)
    db.query(ClanMember).filter_by(user_id=5).delete()
    db.commit()
    PreseasonService()._qualifications(db,db.get(CampaignPreseason,1),utc_now(),persist=True)
    db.commit()
    assert db.get(CampaignPreseason,1).qualifications.get('2',{}).get('slot')==1


def test_postgres_manual_launch_waits_for_pending_fourth_identity_verification(postgres_db,monkeypatch):
    from threading import Event
    from uuid import UUID
    from app.models.clan import ClanMember
    from app.models.external_identity import ExternalPlayerIdentity
    from app.services.external_identity_service import ExternalIdentityService
    from app.core.time import utc_now
    db=postgres_db
    setup(db)
    db.add_all([User(id=i,username=f'Верификация{i}',is_active=True,is_claimed=True,onboarding_completed_at=NOW) for i in range(2,6)])
    db.flush()
    db.add(Clan(id=2,name='Проверяемые',leader_id=2))
    db.flush()
    for i in range(2,6):
        db.add(ExternalPlayerIdentity(user_id=i,source='bfmeladder',external_uuid=str(UUID(int=i)),current_nickname=f'Игрок{i}',current_nickname_key=f'игрок{i}',verification_status='pending' if i==5 else 'verified',verified_at=None if i==5 else NOW))
        db.add(ClanMember(user_id=i,clan_id=2,rank='Воин',joined_at=NOW))
    db.commit()
    captured,release,launch_started=Event(),Event(),Event()
    original=PreseasonService.capture_candidates
    def paused(self,session,*,now):
        original(self,session,now=now)
        captured.set()
        assert release.wait(timeout=10)
    monkeypatch.setattr(PreseasonService,'capture_candidates',paused)
    def verify():
        with Session(db.bind) as session:
            ExternalIdentityService().review_verification(session,target_user=session.get(User,5),reviewer=session.get(User,1),decision='approve',reason='Проверка перед запуском')
    def launch():
        with Session(db.bind) as session:
            launch_started.set()
            value=CycleSeasonLaunchService().start(session,actor_user_id=1,name='Гонка верификации',command_id='verify-race',previous_season_id=1,now=utc_now())
            session.commit()
            return value
    with ThreadPoolExecutor(max_workers=2) as pool:
        verification=pool.submit(verify)
        assert captured.wait(timeout=10)
        started=pool.submit(launch)
        assert launch_started.wait(timeout=10)
        release.set()
        report=started.result(timeout=20)
        verification.result(timeout=20)
    db.expire_all()
    receipt=db.query(CycleStartupClan).filter_by(season_id=report['season_id'],clan_id=2).one()
    assert receipt.slot==1 and len(receipt.selected_four)==4
