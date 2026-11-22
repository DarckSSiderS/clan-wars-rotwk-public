from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.clan import Clan
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.models.cycle_economy import CycleEconomyState, CycleEconomySnapshot, CycleTerritoryUpgrade
from app.models.cycle_income import CycleTerritoryProfile, CycleIncomeAccrual
from app.services.cycle_economy import Resources
from app.services.cycle_income_service import CycleIncomeService
from app.services.cycle_economy_store import EconomyConflict


NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


@pytest.fixture
def income(db):
    season = CampaignSeason(number=1, name='Income', starts_at=NOW,
                            rules_snapshot={'mechanics_version': 'cycle_v1'})
    clan = Clan(name='Income', leader_id=1, created_at=NOW)
    db.add_all([season, clan])
    db.flush()
    state = CycleEconomyState(season_id=season.id, clan_id=clan.id,
                             wallet={k: '0' for k in ('gold', 'iron', 'wood', 'food', 'mithril')})
    db.add(state)
    db.flush()
    return CycleIncomeService(), season, clan, state


def land(db, income, *, history=True):
    service, season, clan, state = income
    row = Territory(name='Land', region='R', svg_path_data='', owner_clan_id=clan.id)
    db.add(row)
    db.flush()
    service.configure_profile(db, season_id=season.id, territory_id=row.id,
                              base=Resources(100, 4), profile_material='iron', now=NOW)
    if history:
        db.add(TerritoryOwnershipHistory(territory_id=row.id, clan_id=clan.id, started_at=NOW))
        db.flush()
    return row


def test_base_idempotent_cas_and_caller_rollback(db, income):
    service, _, _, state = income
    result = service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1), expected_revision=1)
    assert result == Resources(100, 2, 2, 2)
    assert Resources(**state.wallet) == result
    assert service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1)) == Resources()
    with pytest.raises(EconomyConflict):
        service.accrue(db, state_id=state.id, now=NOW + timedelta(days=2), expected_revision=1)
    assert db.query(CycleIncomeAccrual).count() == 1
    db.rollback()
    assert db.query(CycleIncomeAccrual).count() == 0


def test_old_season_holdings_do_not_generate_income_before_starting_choice(db, income):
    service, season, clan, state = income
    territory = land(db, income)
    from app.models.cycle_startup import CycleStartup, CycleStartupClan
    cycle = CampaignCycleRecord(season_id=season.id, number=1, rule_version=1,
        starts_at=NOW, preparation_at=NOW + timedelta(hours=72), dependencies={})
    db.add(cycle)
    db.flush()
    db.add(CycleStartup(season_id=season.id, cycle_id=cycle.id, starts_at=NOW,
        deadline=NOW + timedelta(hours=72), initial_owners={str(territory.id): clan.id}, initialized_at=NOW))
    choice = CycleStartupClan(season_id=season.id, clan_id=clan.id, initial_owned=[territory.id], status='pending')
    db.add(choice)
    db.flush()
    assert service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1)) == Resources(100, 2, 2, 2)
    choice.status = 'claimed'
    choice.claimed_at = NOW + timedelta(days=1)
    choice.selected_lands = [territory.id]
    db.flush()
    assert service.accrue(db, state_id=state.id, now=NOW + timedelta(days=2)) == Resources(200, 6, 2, 2)


def test_transfer_intervals_and_immediate_upgrades(db, income):
    service, season, clan, state = income
    row = land(db, income)
    history = db.query(TerritoryOwnershipHistory).one()
    history.ended_at = NOW + timedelta(hours=12)
    row.owner_clan_id = None
    db.add(CycleTerritoryUpgrade(season_id=season.id, territory_id=row.id, levels={'gold': 1, 'profile': 1}))
    db.flush()
    assert service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1)) == Resources('167.5', 5, 2, 2)


def test_missing_profile_and_history_fail_atomically(db, income):
    service, season, clan, state = income
    row = land(db, income, history=False)
    with pytest.raises(ValueError, match='ownership history'):
        service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1))
    db.add(TerritoryOwnershipHistory(territory_id=row.id, clan_id=clan.id, started_at=NOW))
    db.query(CycleTerritoryProfile).delete()
    db.flush()
    with pytest.raises(ValueError, match='profile'):
        service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1))
    assert Resources(**state.wallet) == Resources()
    assert db.query(CycleIncomeAccrual).count() == 0


def test_profiles_explicit_complete_and_locked_at_preparation(db, income):
    service, season, _, _ = income
    assert not service.has_complete_profiles(db, season_id=season.id)
    row = land(db, income)
    assert service.has_complete_profiles(db, season_id=season.id)
    with pytest.raises(ValueError):
        service.configure_profile(db, season_id=season.id, territory_id=row.id,
                                  base=Resources(100, 4, 4), profile_material='iron', now=NOW)
    db.add(CampaignCycleRecord(season_id=season.id, number=1, rule_version=1,
                              starts_at=NOW, preparation_at=NOW + timedelta(hours=1)))
    db.flush()
    with pytest.raises(ValueError, match='preparation'):
        service.configure_profile(db, season_id=season.id, territory_id=row.id,
                                  base=Resources(150, 6), profile_material='iron', now=NOW + timedelta(hours=1))


def test_future_and_late_clan(db, income):
    service, _, clan, state = income
    clan.created_at = NOW + timedelta(hours=12)
    db.flush()
    with pytest.raises(ValueError, match='future'):
        service.accrue(db, state_id=state.id, now=NOW)
    assert service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1)) == Resources(50, 1, 1, 1)


def test_decimal_residuals_are_polling_independent(db, income):
    service, _, _, state = income
    for second in range(1, 61):
        service.accrue(db, state_id=state.id, now=NOW + timedelta(seconds=second))
    receipt = db.get(CycleIncomeAccrual, state.id)
    from fractions import Fraction
    assert Fraction(state.wallet['gold']) + Fraction(receipt.residuals['gold']) == Fraction(100, 1440)


def test_live_then_frozen_then_rest_effects(db, income):
    service, season, _, state = income
    land(db, income)
    state.relics, state.active_relics = {'white_tree': 3}, ['white_tree']
    cycle = CampaignCycleRecord(season_id=season.id, number=1, rule_version=1,
                                starts_at=NOW, preparation_at=NOW + timedelta(days=1))
    db.add(cycle)
    db.flush()
    db.add(CycleEconomySnapshot(cycle_id=cycle.id, state_id=state.id,
        effects=[dict(key='white_tree', level=1, effect='gold', percent='15')],
        territory_upgrades={}, frozen_at=NOW + timedelta(days=2), state_revision=1))
    db.flush()
    assert service.accrue(db, state_id=state.id, now=NOW + timedelta(days=3)).gold == 685


def test_missing_battle_snapshot_fails(db, income):
    service, season, _, state = income
    land(db, income)
    db.add(CampaignCycleRecord(season_id=season.id, number=1, rule_version=1,
                              starts_at=NOW, preparation_at=NOW))
    db.flush()
    with pytest.raises(ValueError, match='snapshot'):
        service.accrue(db, state_id=state.id, now=NOW + timedelta(days=2))


def test_rest_uses_live_effects_and_upgrade_after_accrual(db, income):
    service, season, _, state = income
    row = land(db, income)
    state.relics, state.active_relics = {'white_tree': 3}, ['white_tree']
    settled = NOW + timedelta(days=3, minutes=5)
    cycle = CampaignCycleRecord(season_id=season.id, number=1, rule_version=1,
                                starts_at=NOW, preparation_at=NOW, settled_at=settled)
    db.add(cycle)
    db.flush()
    db.add(CycleEconomySnapshot(cycle_id=cycle.id, state_id=state.id,
        effects=[dict(key='white_tree', level=1, effect='gold', percent='15')],
        territory_upgrades={}, frozen_at=NOW + timedelta(days=1), state_revision=1))
    db.flush()
    service.accrue(db, state_id=state.id, now=settled)
    db.add(CycleTerritoryUpgrade(season_id=season.id, territory_id=row.id, levels={'gold': 1}))
    db.flush()
    result = service.accrue(db, state_id=state.id, now=settled + timedelta(hours=12))
    assert result.gold == Decimal('141.125')


@pytest.mark.parametrize('profile,base', [
    ('wood', Resources(150, wood=4)), ('food', Resources(100, food=8)),
    ('mithril', Resources(125, mithril=1)), (None, Resources(350)),
])
def test_explicit_material_profiles(db, income, profile, base):
    service, season, _, state = income
    row = land(db, income)
    configured = service.configure_profile(db, season_id=season.id, territory_id=row.id,
                                          base=base, profile_material=profile, now=NOW)
    assert configured.profile_material == profile
    assert service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1)) == Resources(100, 2, 2, 2) + base


@pytest.mark.parametrize('base,profile,error', [
    ({'gold': '100'}, None, TypeError),
    (Resources(100, 4), 'gold', ValueError),
    (Resources(100), 'iron', ValueError),
    (Resources(100, 4), None, ValueError),
])
def test_invalid_admin_profiles(db, income, base, profile, error):
    service, season, _, _ = income
    row = land(db, income)
    with pytest.raises(error):
        service.configure_profile(db, season_id=season.id, territory_id=row.id,
                                  base=base, profile_material=profile, now=NOW)


def test_profile_changes_after_income_rejected(db, income):
    service, season, _, state = income
    row = land(db, income)
    service.accrue(db, state_id=state.id, now=NOW + timedelta(hours=1))
    with pytest.raises(ValueError, match='accrual'):
        service.configure_profile(db, season_id=season.id, territory_id=row.id,
                                  base=Resources(150, 6), profile_material='iron', now=NOW)


def test_unconfigured_unowned_playable_land_blocks_completeness_not_base(db, income):
    service, season, _, state = income
    db.add(Territory(name='Unconfigured', region='R', svg_path_data=''))
    db.flush()
    assert not service.has_complete_profiles(db, season_id=season.id)
    assert service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1)) == Resources(100, 2, 2, 2)


def test_overlapping_history_rejected(db, income):
    service, _, clan, state = income
    row = land(db, income)
    db.add(TerritoryOwnershipHistory(territory_id=row.id, clan_id=clan.id,
                                     started_at=NOW + timedelta(hours=1)))
    db.flush()
    with pytest.raises(ValueError, match='Overlapping'):
        service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1))
    assert state.revision == 1


def test_season_end_caps_credit_and_time_is_explicit(db, income):
    service, season, _, state = income
    season.ends_at = NOW + timedelta(hours=12)
    db.flush()
    assert service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1)) == Resources(50, 1, 1, 1)
    assert service.accrue(db, state_id=state.id, now=NOW + timedelta(days=2)) == Resources()
    with pytest.raises(ValueError, match='backwards'):
        service.accrue(db, state_id=state.id, now=NOW + timedelta(hours=1))
    with pytest.raises(ValueError, match='Timezone'):
        service.accrue(db, state_id=state.id, now=NOW.replace(tzinfo=None))


def test_large_wallet_and_fractional_income_preserved(db, income):
    service, _, _, state = income
    state.wallet = {**state.wallet, 'gold': '1000000000000000000000000000000.1234567890123456789'}
    db.flush()
    service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1))
    assert state.wallet['gold'] == '1000000000000000000000000000100.1234567890123456789'


def test_stale_upgrade_identity_refreshed(db, income):
    from sqlalchemy import update
    service, season, _, state = income
    row = land(db, income)
    upgrade = CycleTerritoryUpgrade(season_id=season.id, territory_id=row.id, levels={'gold': 1})
    db.add(upgrade)
    db.flush()
    db.execute(update(CycleTerritoryUpgrade).values(levels={'gold': 2})
               .execution_options(synchronize_session=False))
    assert upgrade.levels == {'gold': 1}
    assert service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1)).gold == 315


def test_rollback_preserves_previous_receipt(db, income):
    service, _, _, state = income
    service.accrue(db, state_id=state.id, now=NOW + timedelta(hours=1))
    baseline = dict(state.wallet)
    with pytest.raises(RuntimeError):
        with db.begin_nested():
            service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1))
            raise RuntimeError('caller aborts')
    db.refresh(state)
    assert state.wallet == baseline
    assert db.get(CycleIncomeAccrual, state.id).accrued_through.replace(tzinfo=timezone.utc) == NOW + timedelta(hours=1)


def test_receipt_cas_failure_rolls_back_wallet(db, income, monkeypatch):
    from sqlalchemy.sql.dml import Update
    service, _, _, state = income
    service.accrue(db, state_id=state.id, now=NOW + timedelta(hours=1))
    baseline = dict(state.wallet)
    execute = db.execute

    def conflict(statement, *args, **kwargs):
        if isinstance(statement, Update) and statement.table.name == 'cycle_income_accruals':
            return type('ConflictResult', (), {'rowcount': 0})()
        return execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, 'execute', conflict)
    with pytest.raises(EconomyConflict, match='receipt'):
        service.accrue(db, state_id=state.id, now=NOW + timedelta(days=1))
    db.refresh(state)
    assert state.wallet == baseline


def test_lock_order(db, income):
    from sqlalchemy import event
    service, season, _, state = income
    db.add(CampaignCycleRecord(season_id=season.id, number=1, rule_version=1,
                              starts_at=NOW, preparation_at=NOW + timedelta(days=3)))
    db.flush()
    locked = []

    def record(execute_state):
        statement = execute_state.statement
        if getattr(statement, '_for_update_arg', None) is not None:
            locked.extend(table.name for table in statement.get_final_froms())

    event.listen(db, 'do_orm_execute', record)
    try:
        service.accrue(db, state_id=state.id, now=NOW + timedelta(hours=1))
    finally:
        event.remove(db, 'do_orm_execute', record)
    assert locked[:3] == ['campaign_cycles', 'campaign_seasons', 'cycle_economy_states']
