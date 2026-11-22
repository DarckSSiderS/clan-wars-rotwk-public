"""Упаковка проверенной дельты относительно файлов конкретного рабочего релиза."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


ROOT = Path(__file__).resolve().parents[1]
REMOVED_SOURCE = ('app/api/v1/petitions.py', 'app/models/petition.py')
SOURCE_ROOTS = {
    'app': {'.py', '.json', '.csv'}, 'alembic': {'.py'},
    'deploy': {'.py', '.sh', '.ps1', '.service'}, 'scripts': {'.py', '.mjs', '.js', '.sh', '.ps1'},
    'tests': {'.py', '.json', '.html'}, 'frontend/src': {'.js', '.jsx', '.css', '.json', '.svg'},
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files(root):
    candidates = []
    for name, suffixes in SOURCE_ROOTS.items():
        folder = root / name
        if folder.is_dir():
            candidates.extend(p for p in folder.rglob('*') if p.suffix in suffixes)
    for name in ('requirements.txt', 'alembic.ini', 'frontend/package.json', 'frontend/package-lock.json',
                 'frontend/public/map.svg', 'frontend/public/map-interactive.svg'):
        candidates.append(root / name)
    folder = root / 'frontend/dist'
    if folder.is_dir():
        candidates.extend(folder.rglob('*'))
    for path in sorted(set(candidates)):
        relative = path.relative_to(root)
        name = relative.as_posix()
        if (not path.is_file() or path.is_symlink()
                or any(part.startswith('.env') or part in {'__pycache__', 'node_modules', '.tmp'} for part in relative.parts)
                or name.startswith(('frontend/dist/images/', 'frontend/dist/replays/', 'frontend/dist/map_previews/'))):
            continue
        yield name, path


def build_delta(root, baseline, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    temporary = root / '.tmp'
    if (output == temporary or not output.is_relative_to(temporary) or output.exists()
            or not (root / 'frontend/dist/index.html').is_file()
            or not isinstance(baseline, dict) or not isinstance(baseline.get('files'), dict)
            or not isinstance(baseline.get('release'), str)):
        raise ValueError('Нужны manifest рабочего релиза, готовая сборка и новая папка внутри .tmp')
    output.mkdir(parents=True)
    transfer, reuse, hashes = [], [], {}
    for name, path in source_files(root):
        hashes[name] = digest(path)
        (reuse if baseline['files'].get(name) == hashes[name] else transfer).append(name)
    removed = sorted(name for name in REMOVED_SOURCE if name in baseline['files'] and not (root / name).exists())
    manifest = {'base_release': baseline['release'], 'files': hashes,
        'transfer': transfer, 'reuse': reuse, 'remove': removed}
    report = output / 'release-manifest.json'
    report.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf8')
    archive = output / 'delta.tgz'
    with tarfile.open(archive, 'w:gz') as bundle:
        for name in transfer:
            bundle.add(root / name, arcname=name, recursive=False)
        bundle.add(report, arcname=report.name, recursive=False)
    return {'archive': str(archive), 'bytes': archive.stat().st_size, 'sha256': digest(archive),
        'transferred_files': len(transfer), 'reused_files': len(reuse), 'removed_source_files': len(removed)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding='utf8'))
    print(json.dumps(build_delta(ROOT, baseline, args.output), ensure_ascii=False))


if __name__ == '__main__':
    main()
