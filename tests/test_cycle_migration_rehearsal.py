import importlib.util
from pathlib import Path
import sqlite3

import pytest


def module():
    path = Path(__file__).parents[1] / 'scripts/rehearse_cycle_migrations.py'
    spec = importlib.util.spec_from_file_location('cycle_rehearsal', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def source(tmp_path):
    path = tmp_path / 'original.db'
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT);'
            'INSERT INTO users VALUES (1, "Проверка UUID");'
            'CREATE TABLE alembic_version (version_num TEXT);'
            'INSERT INTO alembic_version VALUES ("previous");')
    return path


def test_rehearsal_never_overwrites_source_and_preserves_original_columns(tmp_path, monkeypatch):
    service, original = module(), source(tmp_path)
    before = original.read_bytes()

    def migrate(copy):
        assert copy != original
        with sqlite3.connect(copy) as db:
            db.execute('ALTER TABLE users ADD COLUMN optional_field TEXT')
            db.execute('CREATE TABLE campaign_cycles (id INTEGER PRIMARY KEY)')
            db.execute('UPDATE alembic_version SET version_num="head"')

    monkeypatch.setattr(service, 'run_migrations', migrate)
    report = service.rehearse(original, tmp_path / '.tmp/rehearsal', workspace=tmp_path)
    assert original.read_bytes() == before
    assert report['preserved']['users']['rows'] == 1
    assert report['revision_after'] == ['head']
    assert (tmp_path / '.tmp/rehearsal/report.json').exists()


@pytest.mark.parametrize('target', ['original.db', 'outside', '.tmp/existing'])
def test_rehearsal_refuses_unsafe_or_existing_destination(tmp_path, monkeypatch, target):
    service, original = module(), source(tmp_path)
    existing = tmp_path / '.tmp/existing'
    existing.mkdir(parents=True)
    monkeypatch.setattr(service, 'run_migrations', lambda copy: pytest.fail('Недопустим запуск миграции'))
    with pytest.raises(ValueError):
        service.rehearse(original, tmp_path / target, workspace=tmp_path)


def test_rehearsal_detects_personal_history_loss_without_touching_source(tmp_path, monkeypatch):
    service, original = module(), source(tmp_path)

    def migrate(copy):
        with sqlite3.connect(copy) as db:
            db.execute('DELETE FROM users')

    monkeypatch.setattr(service, 'run_migrations', migrate)
    with pytest.raises(RuntimeError, match='users'):
        service.rehearse(original, tmp_path / '.tmp/rehearsal', workspace=tmp_path)
    with sqlite3.connect(original) as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1
