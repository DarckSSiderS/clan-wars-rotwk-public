"""Пакет выпуска не переносит секреты/тестовые базы и сохраняет старые assets."""
import hashlib
import importlib
import json
import tarfile

import pytest


def packager():
    try:
        return importlib.import_module('scripts.package_production_delta')
    except ModuleNotFoundError:
        pytest.fail('Нет проверяемой упаковки только изменённых файлов')


def put(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding='utf8')
    return path


def test_delta_reuses_matching_assets_and_excludes_private_and_preview_files(tmp_path):
    root = tmp_path / 'project'
    old = put(root, 'frontend/dist/assets/reused.js', 'same')
    put(root, 'frontend/dist/assets/new.js', 'new bundle')
    put(root, 'frontend/dist/index.html', '<script src="/assets/new.js"></script>')
    put(root, 'app/main.py', 'new app')
    for name in ['.env', '.tmp/preview.db', 'frontend/dist-preview/index.html',
                 'frontend/dist/images/private.png', 'frontend/public/images/private.png',
                 'app/__pycache__/cache.pyc', 'frontend/node_modules/dependency.js']:
        put(root, name, 'must not ship')
    baseline = {'release': '/home/clanwar/apps/clanwar/releases/old', 'files': {
        'frontend/dist/assets/reused.js': hashlib.sha256(old.read_bytes()).hexdigest(),
        'frontend/dist/assets/old-open-tab.js': 'old-asset-not-deleted'}}
    result = packager().build_delta(root, baseline, root / '.tmp/release')
    with tarfile.open(result['archive']) as bundle:
        names = set(bundle.getnames())
        manifest = json.load(bundle.extractfile('release-manifest.json'))
    assert names == {'app/main.py', 'frontend/dist/index.html', 'frontend/dist/assets/new.js',
        'release-manifest.json'}
    assert manifest['reuse'] == ['frontend/dist/assets/reused.js']
    assert 'frontend/dist/assets/old-open-tab.js' not in manifest['remove']
    assert result['transferred_files'] == 3


def test_packager_cannot_overwrite_an_existing_package_or_escape_temporary_root(tmp_path):
    root = tmp_path / 'project'
    put(root, 'frontend/dist/index.html', 'ready')
    baseline = {'release': '/home/clanwar/apps/clanwar/releases/old', 'files': {}}
    module = packager()
    for destination in (root / 'release', root.parent / 'elsewhere', root / '.tmp'):
        with pytest.raises(ValueError):
            module.build_delta(root, baseline, destination)
    module.build_delta(root, baseline, root / '.tmp/safe')
    with pytest.raises(ValueError):
        module.build_delta(root, baseline, root / '.tmp/safe')


def test_only_explicitly_removed_source_modules_are_removed(tmp_path):
    root = tmp_path / 'project'
    put(root, 'frontend/dist/index.html', 'ready')
    baseline = {'release': '/home/clanwar/apps/clanwar/releases/old', 'files': {
        'app/api/v1/petitions.py': 'legacy', 'app/models/petition.py': 'legacy',
        'app/services/unrelated.py': 'user-owned-code',
        'frontend/dist/assets/old.js': 'keep-open-tabs'}}
    result = packager().build_delta(root, baseline, root / '.tmp/release')
    manifest = json.loads((root / '.tmp/release/release-manifest.json').read_text())
    assert manifest['remove'] == ['app/api/v1/petitions.py', 'app/models/petition.py']
    assert result['removed_source_files'] == 2
