import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
UVICORN_COMMAND = re.compile(
    r"^.*python(?:\.exe)?\s+-m\s+uvicorn\b.*$",
    flags=re.IGNORECASE | re.MULTILINE,
)


def test_backup_and_restore_assets_have_safety_contracts():
    backup = (ROOT / "deploy/backup/backup.sh").read_text(encoding="utf-8")
    restore = (ROOT / "deploy/backup/restore-smoke.sh").read_text(encoding="utf-8")
    service = (ROOT / "deploy/backup/clanwar-backup.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy/backup/clanwar-backup.timer").read_text(encoding="utf-8")

    assert "set -Eeuo pipefail" in backup
    assert "pg_dump" in backup and "--format=custom" in backup
    assert "sha256sum" in backup and "manifest.sha256" in backup
    assert "tar" in backup and "BACKUP_DESTINATION" in backup
    assert "RETENTION_DAYS" in backup
    assert "mktemp -d" in backup
    assert "set -Eeuo pipefail" in restore
    assert "PRODUCTION_DATABASE_URL" in restore
    assert "RESTORE_DATABASE_URL" in restore
    assert "must differ" in restore
    assert "current_database()" in restore
    assert "sha256sum --check" in restore
    assert "pg_restore" in restore and "--clean" in restore
    assert "OnCalendar=" in timer and "Persistent=true" in timer
    assert "Type=oneshot" in service
    assert "EnvironmentFile=" in service
    assert "ProtectSystem=strict" in service
    assert "ProtectHome=read-only" in service


def test_nginx_template_enforces_https_and_health_proxy():
    nginx = (ROOT / "deploy/nginx/clanwar.conf.template").read_text(encoding="utf-8")

    assert "server_name __DOMAIN__" in nginx
    assert "return 301 https://$host$request_uri" in nginx
    assert "listen 443 ssl http2" in nginx
    assert "ssl_certificate __FULLCHAIN_PATH__" in nginx
    assert "ssl_certificate_key __PRIVATE_KEY_PATH__" in nginx
    assert "location = /health/live" in nginx
    assert "location = /health/ready" in nginx
    assert "proxy_pass http://127.0.0.1:8000" in nginx
    assert "Strict-Transport-Security" in nginx
    assert "client_max_body_size" in nginx


def _assert_sanitized_access_log(source: str) -> None:
    log_format = re.search(
        r"log_format\s+clanwar_sanitized\s+(.+?);",
        source,
        flags=re.DOTALL,
    )
    assert log_format is not None
    format_text = log_format.group(1)
    assert "$uri" in format_text
    assert "$request_uri" not in format_text
    assert "$args" not in format_text
    assert "$query_string" not in format_text
    assert '"$request"' not in format_text
    assert "$http_referer" not in format_text
    assert "access_log /var/log/nginx/access.log clanwar_sanitized;" in source


def test_production_access_logs_cannot_record_oauth_callback_query():
    nginx = (ROOT / "deploy/nginx/clanwar.conf.template").read_text(
        encoding="utf-8"
    )
    bootstrap = (ROOT / "deploy/server-bootstrap.sh").read_text(
        encoding="utf-8"
    )

    _assert_sanitized_access_log(nginx)
    _assert_sanitized_access_log(bootstrap)
    assert "--no-access-log" in bootstrap

    for launcher_path in (ROOT / "run.py", ROOT / "app/main.py"):
        tree = ast.parse(launcher_path.read_text(encoding="utf-8"))
        uvicorn_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "uvicorn"
            and node.func.attr == "run"
        ]
        assert uvicorn_calls
        for call in uvicorn_calls:
            access_log = next(
                (
                    keyword.value
                    for keyword in call.keywords
                    if keyword.arg == "access_log"
                ),
                None,
            )
            assert isinstance(access_log, ast.Constant)
            assert access_log.value is False


def test_documented_uvicorn_commands_disable_access_logs():
    candidate_paths = [
        path
        for path in ROOT.iterdir()
        if path.is_file() and path.suffix.lower() == ".md"
    ]
    for directory in (ROOT / "docs", ROOT / "deploy", ROOT / "scripts"):
        candidate_paths.extend(
            path
            for path in directory.rglob("*")
            if path.is_file()
            and path.suffix.lower()
            in {".md", ".sh", ".ps1", ".bat", ".cmd", ".yml", ".yaml"}
        )

    commands = [
        (path.relative_to(ROOT), command.group(0))
        for path in candidate_paths
        for command in UVICORN_COMMAND.finditer(
            path.read_text(encoding="utf-8")
        )
    ]

    assert commands
    assert [
        (path, command)
        for path, command in commands
        if "--no-access-log" not in command
    ] == []


def test_admin_login_probe_uses_cookie_password_endpoint_without_secret():
    probe = (ROOT / "deploy/verify_admin_login.py").read_text(
        encoding="utf-8"
    )

    assert "/api/v1/auth/password-login" in probe
    assert "/api/v1/auth/token" not in probe
    assert "Authorization" not in probe
    assert "CLANWAR_ADMIN_PASSWORD" in probe
    assert 'headers={"Content-Type": "application/json"}' in probe


def test_production_realtime_uses_redis_and_multiple_web_workers():
    app_service = (ROOT / "deploy/clanwar.service").read_text(encoding="utf-8")
    worker_service = (ROOT / "deploy/clanwar-worker.service").read_text(encoding="utf-8")
    release_script = (ROOT / "deploy/release-existing-server.sh").read_text(encoding="utf-8")

    assert "Requires=postgresql.service redis-server.service" in app_service
    assert "--workers 2" in app_service
    assert "Requires=redis-server.service" in worker_service
    assert '--requirement "$release/requirements.txt"' in release_script
    assert 'ENVIRONMENT=test REDIS_URL="" "$release/.venv/bin/python" -m pytest -q' in release_script

    postgres_cutover = (ROOT / "deploy/switch_to_postgres.sh").read_text(encoding="utf-8")
    assert '"$CURRENT/deploy/clanwar.service"' in postgres_cutover


def test_uploaded_webp_assets_have_an_explicit_browser_safe_content_type():
    main_source = (ROOT / "app/main.py").read_text(encoding="utf-8")

    assert 'mimetypes.add_type("image/webp", ".webp")' in main_source


def test_post_deploy_smoke_checks_current_release_and_public_boundary():
    smoke = (ROOT / "deploy/post-deploy-smoke.ps1").read_text(encoding="utf-8")

    assert "set -euo pipefail" in smoke
    assert "/home/clanwar/apps/clanwar/releases/" in smoke
    assert "systemctl is-active clanwar" in smoke
    assert "systemctl is-active clanwar-worker" in smoke
    assert "/health/live" in smoke
    assert "/health/ready" in smoke
    assert "alembic current" in smoke and '"(head)"' in smoke
    assert "journalctl -u clanwar -u clanwar-worker" in smoke
    assert "/api/v1/auth/session" in smoke
    assert "/api/v1/oauth/session" not in smoke
    assert "Strict-Transport-Security" in smoke
    assert "POST_DEPLOY_SMOKE_OK" in smoke


def test_ci_actions_use_node24_runtime_majors():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert workflow.count("actions/checkout@v5") == 2
    assert "actions/setup-python@v6" in workflow
    assert "actions/setup-node@v5" in workflow
    assert "python-version: '3.11'" in workflow
