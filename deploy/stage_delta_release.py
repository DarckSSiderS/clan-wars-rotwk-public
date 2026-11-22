"""Подготовка отдельного релиза из проверенной дельты без изменения current."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile


REMOVABLE = {'app/api/v1/petitions.py', 'app/models/petition.py'}
EXCLUDED = {'.venv', '.git', 'node_modules', '__pycache__', '.tmp', '.pytest_cache'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_file(source, target):
    # В локальной Windows-песочнице создание hardlink может быть запрещено.
    if os.name == 'nt':
        return shutil.copy2(source, target)
    return os.link(source, target)


def safe_path(name):
    path = PurePosixPath(name)
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or path.is_absolute() or any(p in {'', '.', '..'} for p in name.split('/'))
            or any(p.startswith('.env') or p in EXCLUDED for p in path.parts)
            or name.startswith(('frontend/dist/images/', 'frontend/dist/replays/',
                                'frontend/dist/map_previews/'))):
        raise ValueError('Недопустимый путь дельты')
    return path


def private_file(root, name):
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Файл зависит от внешней ссылки: ' + name)
    parent = path.parent
    while parent != root:
        if parent.is_symlink():
            raise ValueError('Каталог релиза является ссылкой: ' + name)
        parent = parent.parent
    return path


def read_bundle(previous, archive):
    with tarfile.open(archive, 'r:gz') as bundle:
        members = bundle.getmembers()
        names = [m.name for m in members]
        if (len(names) != len(set(names)) or any(not m.isfile() for m in members)
                or sum(m.size for m in members) > 512 * 1024 * 1024
                or 'release-manifest.json' not in names):
            raise ValueError('Некорректный состав архива')
        manifest = json.load(bundle.extractfile('release-manifest.json'))
        if manifest.get('base_release') != str(previous):
            raise ValueError('Рабочий релиз отличается от базового')
        files = manifest['files']
        transfer, reuse, remove = (manifest[key] for key in ('transfer', 'reuse', 'remove'))
        if (not isinstance(files, dict) or any(not isinstance(v, list) for v in (transfer, reuse, remove))
                or len(transfer) != len(set(transfer)) or len(reuse) != len(set(reuse))
                or set(transfer) & set(reuse) or set(files) != set(transfer) | set(reuse)
                or set(names) != set(transfer) | {'release-manifest.json'}
                or not set(remove) <= REMOVABLE or set(remove) & set(files)):
            raise ValueError('Состав дельты не совпадает с manifest')
        for name, sha in files.items():
            safe_path(name)
            if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
                raise ValueError('Неверная контрольная сумма')
        for name in reuse:
            source = private_file(previous, name)
            if not source.is_file() or digest(source) != files[name]:
                raise ValueError('Файл базового релиза изменился: ' + name)
        content = {}
        for name in transfer:
            body = bundle.extractfile(name).read()
            if hashlib.sha256(body).hexdigest() != files[name]:
                raise ValueError('Повреждён файл: ' + name)
            content[name] = body
    return manifest, content


def stage_tree(previous, release, archive):
    previous, release = Path(previous).resolve(), Path(release).absolute()
    if (not previous.is_dir() or release.exists() or release.is_symlink()
            or release.parent.resolve() != previous.parent or release == previous):
        raise ValueError('Нужна новая соседняя папка релиза')
    manifest, content = read_bundle(previous, archive)
    shutil.copytree(previous, release, copy_function=seed_file, symlinks=True,
                    ignore=shutil.ignore_patterns(*EXCLUDED))
    # Новые байты заменяют inode: запись поверх hardlink повредила бы рабочий релиз.
    for name, body in content.items():
        target = release / name
        if not target.parent.resolve().is_relative_to(release.resolve()):
            raise ValueError('Путь ведёт за пределы нового релиза')
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.cutover-new')
        with temporary.open('xb') as stream:
            stream.write(body)
        os.replace(temporary, target)
    for name in manifest['remove']:
        target = release / name
        if not target.parent.resolve().is_relative_to(release.resolve()):
            raise ValueError('Удаление вне нового релиза')
        target.unlink(missing_ok=True)
    for name, sha in manifest['files'].items():
        target = private_file(release, name)
        if digest(target) != sha:
            raise ValueError('Проверка нового релиза не пройдена: ' + name)
    report = release / 'release-manifest.json'
    temporary = report.with_name(report.name + '.cutover-new')
    with temporary.open('x', encoding='utf8') as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2))
    os.replace(temporary, report)
    return {'release': str(release), 'transferred': len(content), 'verified': len(manifest['files'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, default=Path('/home/clanwar/apps/clanwar'))
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--release-name', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[a-zA-Z0-9_-]+', args.release_name):
        raise ValueError('Недопустимое имя релиза')
    root = args.app_root.resolve()
    current = root / 'current'
    if not current.is_symlink() or current.resolve().parent != root / 'releases':
        raise ValueError('Неожиданный путь current')
    print(json.dumps(stage_tree(current.resolve(), root / 'releases' / args.release_name,
                                args.archive), ensure_ascii=False))


if __name__ == '__main__':
    main()
