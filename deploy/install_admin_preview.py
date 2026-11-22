"""Установка отдельного предпросмотра и минимального шлюза существующего сайта."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import tarfile
import time
from urllib.request import build_opener, ProxyHandler, Request


ROOT = Path("/home/clanwar/apps/clanwar-preview")
LIVE = Path("/home/clanwar/apps/clanwar/current")
STAGE = ROOT / "staging/20261024-admin-preview"
OPENER = build_opener(ProxyHandler({}))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args):
    subprocess.run(args, check=True)


def manifest():
    return json.loads((STAGE / "reuse.json").read_text())


def check_live_original():
    data = manifest()
    if str(LIVE.resolve()) != data["release"]:
        raise RuntimeError("Рабочий релиз изменился после подготовки пакета")
    for name, expected in data["production"].items():
        if digest(LIVE / name) != expected:
            raise RuntimeError("Рабочий файл изменился: " + name)


def preview_ready():
    config = json.loads((ROOT / "shared/gateway.json").read_text())
    result = {}
    for path in ["/api/v1/auth/session", "/api/v1/campaign/cycles/1/battles", "/api/v1/campaign/cycles/2"]:
        request = Request("http://127.0.0.1:8182" + path, headers={"X-Clanwar-Preview-Key": config["key"]})
        with OPENER.open(request, timeout=15) as response:
            value = json.load(response)
            result[path] = {"status": response.status, "items": len(value) if isinstance(value, list) else None}
    return result


def prepare(archive):
    archive = archive.resolve()
    if not archive.is_relative_to(ROOT / "inbox") or not archive.is_file() or STAGE.exists():
        raise RuntimeError("Нужен новый пакет в отдельном inbox; существующую копию не перезаписываем")
    STAGE.mkdir(parents=True, mode=0o750)
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                raise RuntimeError("Небезопасный путь пакета")
        bundle.extractall(STAGE, filter="data")
    check_live_original()
    for entry in manifest()["files"]:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("Небезопасный путь статики")
        source = LIVE / "frontend/dist" / relative
        if digest(source) != entry["sha256"]:
            raise RuntimeError("Изменилась исходная статика")
        target = STAGE / "release/frontend/dist" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shared = ROOT / "shared"
    shared.mkdir(mode=0o700)
    shutil.copy2(STAGE / "shared/preview.db", shared / "preview.db")
    (shared / "preview.db").chmod(0o600)
    (ROOT / "current").symlink_to(STAGE / "release", target_is_directory=True)
    unit = Path.home() / ".config/systemd/user/clanwar-preview.service"
    if unit.exists():
        raise RuntimeError("Не перезаписываем существующую пользовательскую службу")
    unit.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STAGE / "clanwar-preview.service", unit)
    command("systemctl", "--user", "daemon-reload")
    command("systemctl", "--user", "enable", "--now", "clanwar-preview")
    failure = None
    for _ in range(30):
        try:
            result = preview_ready()
            print(json.dumps({"preview": result, "production_changed": False}))
            return
        except Exception as exc:
            failure = exc
            time.sleep(1)
    raise RuntimeError("Предпросмотр не прошёл проверку готовности") from failure


def activate():
    preview_ready()
    check_live_original()
    main = LIVE / "app/main.py"
    original = main.read_bytes()
    anchor = b'app.mount("/", SPAStaticFiles(directory=str(frontend_dir), html=True), name="frontend")'
    if original.count(anchor) != 1 or b"admin_preview_gateway" in original:
        raise RuntimeError("Неожиданная точка подключения шлюза")
    gateway = LIVE / "app/admin_preview_gateway.py"
    if gateway.exists():
        raise RuntimeError("Модуль шлюза уже существует; не перезаписываем его")
    backup = ROOT / "backups/20261024-admin-preview"
    backup.mkdir(parents=True, mode=0o700)
    saved = backup / "main.py.before"
    if saved.exists():
        raise RuntimeError("Резервная копия уже существует")
    shutil.copy2(main, saved)
    saved.chmod(0o600)
    hook = (
        b"from app.admin_preview_gateway import install_admin_preview\n"
        b'install_admin_preview(app, config_path="/home/clanwar/apps/clanwar-preview/shared/gateway.json")\n'
    )
    candidate = backup / "main.py.next"
    candidate.write_bytes(original.replace(anchor, hook + anchor, 1))
    py_compile.compile(str(candidate), doraise=True)
    gateway_source = ROOT / "current/app/admin_preview_gateway.py"
    py_compile.compile(str(gateway_source), doraise=True)
    shutil.copy2(gateway_source, gateway)
    shutil.copymode(main, candidate)
    try:
        os.replace(candidate, main)
        command("sudo", "-n", "/usr/bin/systemctl", "restart", "clanwar", "clanwar-worker")
        for _ in range(30):
            try:
                with OPENER.open("http://127.0.0.1:8000/health/ready", timeout=3) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError("Рабочее приложение не прошло проверку готовности")
    except BaseException:
        restore = backup / "main.py.restore"
        shutil.copy2(saved, restore)
        os.replace(restore, main)
        command("sudo", "-n", "/usr/bin/systemctl", "restart", "clanwar", "clanwar-worker")
        raise
    unchanged = {}
    for name, expected in manifest()["production"].items():
        if name != "app/main.py":
            unchanged[name] = digest(LIVE / name) == expected
    if not all(unchanged.values()):
        raise RuntimeError("Изменились защищённые файлы")
    report = {"backup": str(saved), "gateway_enabled": True, "unchanged": unchanged,
              "main_before": hashlib.sha256(original).hexdigest(), "main_after": digest(main)}
    (ROOT / "installation-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "activate", "check"])
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.archive)
    elif args.mode == "activate":
        activate()
    else:
        print(json.dumps(preview_ready()))
