"""Staging не переписывает hardlink старого релиза и не принимает обход путей."""
import hashlib
import importlib
import io
import json
from pathlib import Path
import tarfile

import pytest


def installer():
    try:
        return importlib.import_module('deploy.stage_delta_release')
    except ModuleNotFoundError:
        pytest.fail('Нет безопасного staging для дельты')


def archive(path, base, entries, *, member=None):
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in entries.items()}
    manifest = {'base_release': str(base), 'files': hashes, 'transfer': list(entries), 'reuse': [], 'remove': []}
    with tarfile.open(path, 'w:gz') as bundle:
        content = json.dumps(manifest).encode()
        info = tarfile.TarInfo('release-manifest.json')
        info.size = len(content)
        bundle.addfile(info, io.BytesIO(content))
        for name, body in entries.items():
            info = tarfile.TarInfo(member or name)
            info.size = len(body)
            bundle.addfile(info, io.BytesIO(body))


def test_stage_keeps_previous_source_unchanged_and_retains_old_browser_assets(tmp_path):
    old = tmp_path / 'releases/old'
    (old / 'app').mkdir(parents=True)
    (old / 'app/main.py').write_bytes(b'previous app')
    (old / 'frontend/dist/assets').mkdir(parents=True)
    (old / 'frontend/dist/assets/open-tab.js').write_bytes(b'keep old chunk')
    bundle = tmp_path / 'delta.tgz'
    archive(bundle, old, {'app/main.py': b'next app', 'frontend/dist/index.html': b'new html'})
    new = old.parent / 'next'
    installer().stage_tree(old, new, bundle)
    assert (old / 'app/main.py').read_bytes() == b'previous app'
    assert (new / 'app/main.py').read_bytes() == b'next app'
    assert (new / 'frontend/dist/assets/open-tab.js').read_bytes() == b'keep old chunk'


@pytest.mark.parametrize('path', ['../escape.py', '/tmp/outside.py', 'app/../../escape.py',
    '.env', 'frontend/dist/images/private.png'])
def test_stage_rejects_unsafe_paths_before_creating_a_release(tmp_path, path):
    old = tmp_path / 'releases/old'
    old.mkdir(parents=True)
    bundle = tmp_path / 'delta.tgz'
    archive(bundle, old, {path: b'bad'})
    new = old.parent / 'next'
    with pytest.raises(ValueError):
        installer().stage_tree(old, new, bundle)
    assert not new.exists()


def test_stage_rejects_wrong_baseline_and_checksum(tmp_path):
    old = tmp_path / 'releases/old'
    old.mkdir(parents=True)
    bundle = tmp_path / 'delta.tgz'
    archive(bundle, Path('/different/base'), {'app/main.py': b'new'})
    with pytest.raises(ValueError):
        installer().stage_tree(old, old.parent / 'next', bundle)
    archive(bundle, old, {'app/main.py': b'new'}, member='app/other.py')
    with pytest.raises(ValueError):
        installer().stage_tree(old, old.parent / 'next', bundle)
    assert not (old.parent / 'next').exists()


def test_existing_manifest_temporary_file_is_not_truncated(tmp_path):
    old = tmp_path / 'releases/old'
    old.mkdir(parents=True)
    sentinel = old / 'release-manifest.json.cutover-new'
    sentinel.write_bytes(b'never truncate a reused inode')
    bundle = tmp_path / 'delta.tgz'
    archive(bundle, old, {'app/main.py': b'new'})
    with pytest.raises(FileExistsError):
        installer().stage_tree(old, old.parent / 'next', bundle)
    assert sentinel.read_bytes() == b'never truncate a reused inode'


def test_reuse_rejects_external_parent_symlink(tmp_path):
    old = tmp_path / 'releases/old'
    old.mkdir(parents=True)
    external = tmp_path / 'shared-app'
    external.mkdir()
    (external / 'main.py').write_bytes(b'outside')
    try:
        (old / 'app').symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip('Создание symlink запрещено локальной средой')
    manifest = {'base_release': str(old), 'files': {'app/main.py': hashlib.sha256(b'outside').hexdigest()},
                'transfer': [], 'reuse': ['app/main.py'], 'remove': []}
    bundle = tmp_path / 'delta.tgz'
    with tarfile.open(bundle, 'w:gz') as tar:
        body = json.dumps(manifest).encode()
        item = tarfile.TarInfo('release-manifest.json')
        item.size = len(body)
        tar.addfile(item, io.BytesIO(body))
    with pytest.raises(ValueError):
        installer().stage_tree(old, old.parent / 'next', bundle)
    assert not (old.parent / 'next').exists()
