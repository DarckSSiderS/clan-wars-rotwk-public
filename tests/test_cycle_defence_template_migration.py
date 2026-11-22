import importlib.util
import ast
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from app.database import Base
from app.models.cycle_defence_template import CycleDefenceTemplate


def test_defence_template_revision_is_unique_and_has_the_agreed_parent():
    revisions = {}
    for path in (Path(__file__).parents[1] / 'alembic/versions').glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        values = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                  and node.targets[0].id in {'revision', 'down_revision'}}
        if 'revision' not in values:
            continue
        revision = values['revision']
        assert revision not in revisions, f'Duplicate migration revision: {revision}'
        revisions[revision] = values.get('down_revision')
    assert revisions['r0f1g2h3i4j5'] == 'q9f0g1h2i3j4'
    if 's1g2h3i4j5k6' in revisions:
        assert revisions['s1g2h3i4j5k6'] == 'r0f1g2h3i4j5'


def test_defence_template_migration_schema_chain_and_no_historical_backfill():
    root = Path(__file__).parents[1]
    path = root / 'alembic/versions/r0f1g2h3i4j5_add_cycle_defence_templates.py'
    spec = importlib.util.spec_from_file_location('defence_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == 'r0f1g2h3i4j5'
    assert migration.down_revision == 'q9f0g1h2i3j4'
    engine = create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            table = CycleDefenceTemplate.__table__
            Base.metadata.create_all(connection, tables=[t for t in Base.metadata.sorted_tables if t is not table])
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            inspector = inspect(connection)
            assert {c['name'] for c in inspector.get_columns(table.name)} == set(table.columns.keys())
            assert any(set(c['column_names']) == {'season_id', 'clan_id'}
                       for c in inspector.get_unique_constraints(table.name))
            assert {tuple(f['constrained_columns']) for f in inspector.get_foreign_keys(table.name)} == {
                ('season_id',), ('clan_id',), ('updated_by_user_id',)}
            assert connection.execute(text('SELECT COUNT(*) FROM cycle_defence_templates')).scalar_one() == 0
            migration.downgrade()
            assert table.name not in inspect(connection).get_table_names()
            assert 'campaign_cycle_plans' in inspect(connection).get_table_names()
    finally:
        engine.dispose()
