"""Локальные защитные проверки сценария выпуска, без доступа к серверу."""

from pathlib import Path
import re
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'deploy' / 'release-existing-server.sh'


def test_release_never_automatically_downgrades_database():
    source = SCRIPT.read_text(encoding='utf-8')
    assert not re.search(r'\balembic\s+downgrade\b', source)


def test_release_requires_existing_backup_before_stopping_services_or_migrating():
    source = SCRIPT.read_text(encoding='utf-8')
    backup = source.index('[[ ! -s "$database_backup" ]]')
    stop = source.index('sudo systemctl stop clanwar clanwar-worker', backup)
    migrate = source.index('"$release/.venv/bin/python" -m alembic upgrade head')
    assert backup < stop < migrate
    assert source.index('migration_attempted=1', stop) < migrate


def test_failed_schema_change_does_not_restart_old_code():
    source = SCRIPT.read_text(encoding='utf-8')
    handler = source.split('rollback_failed_release() {', 1)[1].split('\n}\n', 1)[0]
    protected, before_migration = handler.split('\n  else\n', 1)
    assert '"$migration_attempted" -eq 1' in protected
    assert 'systemctl stop clanwar clanwar-worker' in protected
    assert 'systemctl restart' not in protected
    assert 'ln -sfn' not in protected
    assert 'systemctl restart' in before_migration


def test_housekeeping_cannot_stop_an_already_healthy_release():
    source = SCRIPT.read_text(encoding='utf-8')
    healthy = source.index('sudo systemctl is-active --quiet clanwar-worker')
    disable = source.index('trap - ERR', healthy)
    cleanup = source.index('for old_release in', healthy)
    assert healthy < disable < cleanup
    assert '[[ ! -f "$database_backup" ]]' in source


@pytest.mark.parametrize('attempted', [0, 1])
def test_rollback_handler_with_fake_commands(tmp_path, attempted):
    bash = shutil.which('bash')
    if not bash:
        pytest.skip('Bash отсутствует; статические защитные проверки выполняются отдельно')
    source = SCRIPT.read_text(encoding='utf-8')
    handler = source.split('rollback_failed_release() {', 1)[1].split('\n}\n', 1)[0]
    program = f'''set -e
migration_attempted={attempted}
services_stopped=1
previous=previous
current=current
database_backup=backup
sudo() {{ printf 'SUDO %s\\n' "$*"; }}
ln() {{ printf 'LINK %s\\n' "$*"; }}
rollback_failed_release() {{{handler}
}}
false || rollback_failed_release
'''
    result = subprocess.run([bash, '-c', program], cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 1
    if attempted:
        assert 'systemctl stop' in result.stdout
        assert 'LINK' not in result.stdout and 'restart' not in result.stdout
    else:
        assert 'LINK' in result.stdout and 'restart' in result.stdout
