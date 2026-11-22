"""Проверяет миграции только на новой изолированной копии SQLite внутри .tmp."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PROTECTED = frozenset({
    'users', 'external_player_identities', 'external_player_aliases',
    'matches', 'match_participants', 'achievements', 'user_achievements',
    'clans', 'clan_members', 'clan_membership_periods', 'campaign_seasons',
    'campaign_season_clan_results', 'quests', 'user_quests',
    'clan_wars', 'clan_war_participants', 'clan_war_match_results',
    'war_deployments', 'war_deployment_members', 'war_score_adjustments',
    'user_titles', 'user_items', 'titles', 'clan_invites', 'clan_applications',
})


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def revisions(connection):
    present = connection.execute("SELECT name FROM sqlite_master WHERE name='alembic_version'").fetchone()
    return sorted(row[0] for row in connection.execute('SELECT version_num FROM alembic_version')) if present else []


def fingerprints(connection, columns=None):
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    result = {}
    for name in sorted(PROTECTED & tables if columns is None else columns):
        if name not in tables:
            raise RuntimeError(f'Миграция удалила сохраняемую таблицу {name}')
        names = columns[name] if columns is not None else [row[1] for row in connection.execute(f'PRAGMA table_info({quote(name)})')]
        rows = [json.dumps(list(row), ensure_ascii=False, separators=(',', ':'),
            default=lambda value: {'bytes': value.hex()}) for row in connection.execute(
                f'SELECT {", ".join(quote(column) for column in names)} FROM {quote(name)}')]
        checksum = hashlib.sha256(json.dumps(sorted(rows), ensure_ascii=False).encode('utf-8')).hexdigest()
        result[name] = dict(columns=names, rows=len(rows), sha256=checksum)
    return result


def run_migrations(copy):
    environment = {**os.environ, 'DATABASE_URL': 'sqlite:///' + copy.as_posix()}
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
        cwd=ROOT, env=environment, check=True)


def rehearse(source, destination, *, workspace=ROOT):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    temporary = (Path(workspace).resolve() / '.tmp').resolve()
    if (not source.is_file() or not destination.is_relative_to(temporary)
            or destination == temporary or destination.exists() or source.is_relative_to(destination)):
        raise ValueError('Нужна существующая исходная база и новая папка копии внутри .tmp')
    destination.mkdir(parents=True, exist_ok=False)
    copy = destination / 'rehearsal.db'
    # Штатное резервное копирование учитывает WAL; источник открыт только для чтения.
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as original:
        with sqlite3.connect(copy) as target:
            original.backup(target)
    with sqlite3.connect(copy) as target:
        before = fingerprints(target)
        previous_revision = revisions(target)
    run_migrations(copy)
    with sqlite3.connect(copy) as target:
        after = fingerprints(target, {name: item['columns'] for name, item in before.items()})
        revision = revisions(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Проверка целостности копии не пройдена')
    for name, expected in before.items():
        if after[name] != expected:
            raise RuntimeError(f'Миграция изменила сохраняемые данные таблицы {name}')
    report = dict(source=str(source), copy=str(copy), revision_before=previous_revision,
        revision_after=revision, preserved=after, source_opened_read_only=True)
    (destination / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    result = rehearse(arguments.source, arguments.output)
    print(json.dumps(dict(revision_before=result['revision_before'], revision_after=result['revision_after'],
        preserved_tables=len(result['preserved']), report=str(arguments.output / 'report.json')),
        ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
