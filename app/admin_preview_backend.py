"""Запуск изолированной версии, доступной только через административный шлюз."""

import argparse
import hmac
import json
import os
from pathlib import Path
import secrets
from threading import Lock

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response


class PreviewBackendAuth:
    def __init__(self, app, *, key, token_provider=None):
        self.app = app
        self.key = key
        self.token_provider = token_provider or self.session_token
        self.token = None
        self.lock = Lock()

    def session_token(self):
        from app.database import SessionLocal
        from app.models.user import User
        from app.services.session_service import InvalidSession, SessionService

        with self.lock, SessionLocal() as db:
            service = SessionService()
            if self.token:
                try:
                    service.resolve(db, self.token, touch=False)
                    return self.token
                except InvalidSession:
                    pass
            user = db.query(User).filter_by(username="local-review").one()
            if not user.is_active or not user.role or user.role.name != "admin":
                raise RuntimeError("Тестовый администратор недоступен")
            self.token = service.issue(db, user).token
            return self.token

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        supplied = Request(scope).headers.get("x-clanwar-preview-key", "")
        if not hmac.compare_digest(supplied, self.key):
            return await Response(status_code=404)(scope, receive, send)
        path = scope.get("path", "")
        if path.startswith(("/api/v1/auth/arena/", "/api/v1/scheduler/")):
            return await Response(status_code=403)(scope, receive, send)
        token = await run_in_threadpool(self.token_provider)
        headers = [
            (key, value) for key, value in scope.get("headers", [])
            if key.lower() not in {b"cookie", b"x-clanwar-preview-key", b"authorization"}
        ]
        headers.append((b"cookie", f"clanwar_preview_session={token}".encode("ascii")))
        return await self.app({**scope, "headers": headers}, receive, send)


def install_preview_controls(app, *, database, read=None, switch=None):
    """Only the private entrypoint installs these routes, never app.main."""
    from typing import Literal
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel, ConfigDict

    if read is None or switch is None:
        from app.services.preview_scenario_service import read_preview_scenario, switch_preview_scenario
        read = read or read_preview_scenario
        switch = switch or switch_preview_scenario

    class ScenarioRequest(BaseModel):
        model_config = ConfigDict(extra='forbid', strict=True)
        mode: Literal['preparation', 'battle']
        confirm_reset: bool = False

    router = APIRouter(prefix='/api/v1/admin-preview')

    @router.get('/scenario')
    def scenario():
        try:
            return read(database)
        except (ValueError, RuntimeError) as error:
            raise HTTPException(status_code=409, detail='Тестовый сценарий ещё не подготовлен.') from error

    @router.post('/scenario')
    def change_scenario(body: ScenarioRequest):
        try:
            return switch(database, body.mode, confirm_reset=body.confirm_reset)
        except (ValueError, RuntimeError) as error:
            raise HTTPException(status_code=409, detail='Не удалось переключить тестовый сценарий. Обновите страницу и подтвердите сброс.') from error

    start = len(app.router.routes)
    app.include_router(router)
    controls = app.router.routes[start:]
    del app.router.routes[start:]
    # app.main already mounted its SPA; API routes must precede that catch-all.
    app.router.routes[0:0] = controls


def main():
    parser = argparse.ArgumentParser(description="Закрытый предпросмотр на loopback")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--origin", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    shared = root / "shared"
    database = shared / "preview.db"
    if not database.is_file() or root.name != "clanwar-preview":
        raise SystemExit("Нужна отдельная база clanwar-preview/shared/preview.db")
    config_path = shared / "gateway.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config["public_origin"] != args.origin:
            raise SystemExit("Origin не совпадает с существующим предпросмотром")
    else:
        config = {"key": secrets.token_urlsafe(48), "app_secret": secrets.token_urlsafe(48), "public_origin": args.origin}
        fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle)
    # Настройки задаются до первого импорта приложения, без чтения production .env.
    os.environ.update({
        "ENVIRONMENT": "development", "DEBUG": "false",
        "DATABASE_URL": "sqlite:///" + database.as_posix(),
        "SECRET_KEY": config["app_secret"],
        "SESSION_COOKIE_NAME": "clanwar_preview_session",
        "CORS_ORIGINS": json.dumps([args.origin]),
        "DISCORD_ENABLED": "false", "DISCORD_BOT_TOKEN": "",
        "REDIS_URL": "", "BFME_OAUTH_ENABLED": "false",
        "BFME_OAUTH_CLIENT_SECRET": "", "SMTP_HOST": "", "SMTP_PASSWORD": "",
        "LADDER_PUBLIC_API_ENABLED": "false", "LADDER_PUBLIC_API_TOKEN": "",
        "UPLOAD_DIR": str(shared / "images"),
        "REPLAY_STORAGE_DIR": str(shared / "replays"),
        "MAP_PREVIEW_STORAGE_DIR": str(shared / "map_previews"),
        "BOOTSTRAP_TEST_ADMIN_ENABLED": "false",
    })
    os.environ.pop("ADMIN_PREVIEW_CONFIG", None)
    from app.main import app
    import uvicorn

    install_preview_controls(app, database=database)
    app.add_middleware(PreviewBackendAuth, key=config["key"])
    uvicorn.run(app, host="127.0.0.1", port=8182, access_log=False)


if __name__ == "__main__":
    main()
