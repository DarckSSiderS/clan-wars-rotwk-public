"""Новые административные команды и шаблон на изолированной PostgreSQL."""

from datetime import timedelta

import pytest

from app.models.cycle_defence_template import CycleDefenceTemplate
from app.models.cycle_economy import CycleEconomyState
from app.models.operation import AdminAuditLog
from app.models.role import Role
from app.models.territory import TerritoryOwnershipHistory
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_admin_economy_service import CycleAdminEconomyService
from app.services.cycle_administration_service import CycleAdministrationService
from app.services.cycle_economy import Resources
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_income_service import CycleIncomeService
from app.services.cycle_plan_service import CyclePlanService
from tests.test_campaign_cycle_store import START
from tests.test_cycle_administration import setup_world as recovery_world
from tests.test_cycle_commands_postgres import parallel
from tests.test_cycle_plan_service import setup_world


@pytest.mark.parametrize('same_command', [True, False])
def test_parallel_treasury_corrections_keep_one_write_and_receipt(postgres_db, monkeypatch, same_command):
    db = postgres_db
    users, clan, land, cycle = setup_world(db)
    users[0].role = db.get(Role, 1)
    clan.created_at = START
    db.add(TerritoryOwnershipHistory(territory_id=land.id, clan_id=clan.id, started_at=START))
    db.flush()
    CycleIncomeService().configure_profile(db, season_id=cycle.season_id, territory_id=land.id,
        base=Resources(100, 4), profile_material='iron', now=START)
    state = CycleEconomyStore().ensure_state(db, season_id=cycle.season_id, clan_id=clan.id)
    from app.core import time as clock
    monkeypatch.setattr(clock, 'utc_now', lambda: START)
    args = dict(clan_id=clan.id, actor_id=users[0].id, season_id=cycle.season_id,
        expected_revision=state.revision, reason='Проверка одновременного исправления',
        wallet=dict(gold='1234.125', iron='42', wood='30', food='20', mithril='5'))
    state_id, before_revision = state.id, state.revision
    db.commit()
    results = parallel(db, lambda session, index: CycleAdminEconomyService().correct(session,
        **args, command_id='same-treasury' if same_command else f'treasury-{index}'))
    if same_command:
        assert results[0] == results[1] and results[0][0] == 'ok'
    else:
        assert sorted(status for status, _ in results) == ['conflict', 'ok']
    db.expire_all()
    saved = db.get(CycleEconomyState, state_id)
    assert saved.wallet == args['wallet']
    assert saved.revision == before_revision + 1
    assert db.query(AdminAuditLog).filter_by(action=CycleAdminEconomyService.action).count() == 1


@pytest.mark.parametrize('same_command', [True, False])
def test_parallel_recovery_moves_preparation_only_once(postgres_db, same_command):
    db = postgres_db
    users, _, _, cycle = recovery_world(db)
    now = CampaignCycleStore.timeline(cycle).battle_at + timedelta(days=1)
    args = dict(cycle_id=cycle.id, actor_user_id=users[0].id, expected_revision=cycle.revision,
        reason='Сервер пропустил подготовку', now=now)
    cycle_id = cycle.id
    db.commit()
    results = parallel(db, lambda session, index: CycleAdministrationService().recover_preparation(session,
        **args, command_id='same-recovery' if same_command else f'recovery-{index}'))
    if same_command:
        assert results[0] == results[1] and results[0][0] == 'ok'
    else:
        assert sorted(status for status, _ in results) == ['conflict', 'ok']
    db.expire_all()
    saved = CampaignCycleStore()._locked(db, cycle_id)
    assert CampaignCycleStore.timeline(saved).preparation_at == now
    assert CampaignCycleStore.timeline(saved).battle_at == now + timedelta(hours=24)
    assert saved.planning_snapshot is not None
    assert db.query(AdminAuditLog).filter_by(action='cycle_preparation_recovered').count() == 1


def test_parallel_template_creation_does_not_overwrite_another_assignment(postgres_db):
    db = postgres_db
    users, clan, land, cycle = setup_world(db)
    now = CampaignCycleStore.timeline(cycle).preparation_at
    CyclePlanService().capture_preparation(db, cycle_id=cycle.id, now=now)
    args = dict(cycle_id=cycle.id, clan_id=clan.id, actor_user_id=users[0].id,
        expected_revision=0, now=now)
    players, territory_id = [users[1].id, users[2].id], land.id
    db.commit()
    results = parallel(db, lambda session, index: CyclePlanService().save_defence_template(session,
        **args, assignments=[dict(user_id=players[index], territory_id=territory_id)]))
    assert sorted(status for status, _ in results) == ['conflict', 'ok']
    db.expire_all()
    rows = db.query(CycleDefenceTemplate).all()
    assert len(rows) == 1 and rows[0].revision == 1
    winner = next(value for status, value in results if status == 'ok')
    assert rows[0].assignments == winner['assignments']
