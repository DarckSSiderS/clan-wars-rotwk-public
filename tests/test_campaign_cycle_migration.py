import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect


def test_cycle_migration_roundtrip_matches_models_on_disposable_database():
    path = Path(__file__).parents[1] / 'alembic/versions/e7t8u9v0w1x2_add_campaign_cycles.py'
    spec = importlib.util.spec_from_file_location('cycle_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            parents = MetaData()
            for name in ('users', 'clans', 'territories', 'campaign_seasons'):
                Table(name, parents, Column('id', Integer, primary_key=True))
            parents.create_all(connection)
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            battle_path = path.parent / 'f8u9v0w1x2y3_add_cycle_battle_accounting.py'
            battle_spec = importlib.util.spec_from_file_location('battle_migration', battle_path)
            battles = importlib.util.module_from_spec(battle_spec)
            battle_spec.loader.exec_module(battles)
            battles.op = migration.op
            battles.upgrade()
            additions = []
            for filename in ('g9v0w1x2y3z4_add_cycle_economy.py', 'h0w1x2y3z4a5_add_cycle_diplomacy.py', 'i1x2y3z4a5b6_add_cycle_scouting.py', 'j2y3z4a5b6c7_add_cycle_remaining_storage.py', 'q9f0g1h2i3j4_add_cycle_scout_player.py'):
                extra_spec = importlib.util.spec_from_file_location(filename.split('_')[0], path.parent / filename)
                extra = importlib.util.module_from_spec(extra_spec)
                extra_spec.loader.exec_module(extra)
                extra.op = migration.op
                extra.upgrade()
                additions.append(extra)
            inspector = inspect(connection)
            from app.models.campaign_cycle import CampaignCycleRecord, CampaignCyclePlan
            for model in (CampaignCycleRecord, CampaignCyclePlan):
                assert {c['name'] for c in inspector.get_columns(model.__tablename__)} == set(model.__table__.columns.keys())
            from app.models.cycle_battle import CycleTerritoryBattle, CycleMatchContribution, CycleScoreAdjustment
            for model in (CycleTerritoryBattle, CycleMatchContribution, CycleScoreAdjustment):
                assert {c['name'] for c in inspector.get_columns(model.__tablename__)} == set(model.__table__.columns.keys())
            from app.models.cycle_economy import CycleEconomyState, CycleEconomySnapshot, CycleTerritoryUpgrade
            from app.models.cycle_diplomacy import CycleDiplomacyPair, CycleDiplomacyProposal, CycleDiplomacyEvent
            from app.models.campaign_cycle import CampaignCyclePlanRevision, CycleScoutRequest
            for model in (CycleEconomyState, CycleEconomySnapshot, CycleTerritoryUpgrade,
                          CycleDiplomacyPair, CycleDiplomacyProposal, CycleDiplomacyEvent,
                          CampaignCyclePlanRevision, CycleScoutRequest):
                assert {c['name'] for c in inspector.get_columns(model.__tablename__)} == set(model.__table__.columns.keys())
            from app.models.cycle_income import CycleTerritoryProfile, CycleIncomeAccrual
            from app.models.cycle_market import CycleMarketOffer, CycleMarketCaravan, CycleMarketCommand
            from app.models.cycle_startup import CycleStartup, CycleStartupClan, CycleStartupIdentity
            from app.models.cycle_reinforcement_state import CycleReinforcementState
            for model in (CycleTerritoryProfile, CycleIncomeAccrual, CycleMarketOffer, CycleMarketCaravan,
                          CycleMarketCommand, CycleStartup, CycleStartupClan, CycleStartupIdentity, CycleReinforcementState):
                assert {c['name'] for c in inspector.get_columns(model.__tablename__)} == set(model.__table__.columns.keys())
            for extra in reversed(additions):
                extra.downgrade()
            battles.downgrade()
            migration.downgrade()
            assert set(inspect(connection).get_table_names()) == set(parents.tables)
    finally:
        engine.dispose()
