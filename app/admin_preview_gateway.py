"""Закрытый шлюз к отдельной тестовой версии без обновления боевых механик."""

import json
import logging
import os
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import httpx
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response


PREFIX = "/admin/preview"
UPSTREAM = "http://127.0.0.1:8182"
logger = logging.getLogger(__name__)
PRIVATE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}
LAUNCHER = '''<aside style="background:#111411;border-bottom:1px solid #74633e;padding:12px 24px;text-align:right;font:14px Arial,sans-serif"><a href="/admin/preview/" target="_blank" rel="noopener" style="display:inline-block;padding:10px 18px;background:#d3bc83;color:#111411;border-radius:4px;text-decoration:none;font-weight:700">Предпросмотр новой версии</a></aside>'''


def is_admin_session(scope):
    from app.config import settings
    from app.database import SessionLocal
    from app.services.session_service import InvalidSession, SessionService

    token = Request(scope).cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        return False
    try:
        with SessionLocal() as db:
            session = SessionService().resolve(db, token, touch=False)
            user = session.user
            return bool(
                user.is_active and user.role and user.role.name == "admin"
                and not session.is_impersonation
            )
    except InvalidSession:
        return False
    except Exception:
        logger.warning("Не удалось проверить доступ к предпросмотру")
        return False


class AdminPreviewGateway:
    def __init__(self, app, *, config_path, admin_check=None, transport=None):
        self.app = app
        self.config_path = Path(config_path)
        self.admin_check = admin_check or is_admin_session
        self.transport = transport

    def config(self):
        try:
            config = json.loads(self.config_path.read_text(encoding="utf-8"))
            origin = urlsplit(config["public_origin"])
            if (
                len(config["key"]) < 32
                or origin.scheme not in {"http", "https"}
                or not origin.hostname or origin.username or origin.password
                or origin.path or origin.query or origin.fragment
            ):
                return None
            return config
        except (OSError, ValueError, KeyError, TypeError):
            return None

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        preview = path == PREFIX or path.startswith(PREFIX + "/")
        portal = path.rstrip("/") == "/admin" and scope.get("method") == "GET"
        if scope["type"] != "http" or not (preview or portal):
            return await self.app(scope, receive, send)
        allowed = await run_in_threadpool(self.admin_check, scope)
        if not allowed:
            if preview:
                return await Response(status_code=404, headers=PRIVATE_HEADERS)(scope, receive, send)
            return await self.app(scope, receive, send)
        config = self.config()
        if portal:
            if not config:
                return await self.app(scope, receive, send)
            return await self.admin_document(scope, receive, send)
        if not config:
            return await self.unavailable(scope, receive, send)
        if path == PREFIX:
            return await RedirectResponse(PREFIX + "/", headers=PRIVATE_HEADERS)(scope, receive, send)
        request = Request(scope, receive)
        suffix = path[len(PREFIX):]
        if "\\" in suffix or any(segment in {".", ".."} for segment in suffix.split("/")):
            return await Response(status_code=400, headers=PRIVATE_HEADERS)(scope, receive, send)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("origin") != config["public_origin"] or suffix.startswith("/api/v1/auth/"):
                return await Response(status_code=403, headers=PRIVATE_HEADERS)(scope, receive, send)
        body = await request.body()
        if len(body) > 10 * 1024 * 1024:
            return await Response(status_code=413, headers=PRIVATE_HEADERS)(scope, receive, send)
        url = UPSTREAM + quote(suffix, safe="/:@-._~!$&'()*+,;=")
        if scope.get("query_string"):
            url += "?" + scope["query_string"].decode("ascii")
        headers = {"X-Clanwar-Preview-Key": config["key"]}
        for key in ("content-type", "accept", "range"):
            if key in request.headers:
                headers[key] = request.headers[key]
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=30, trust_env=False) as client:
                upstream = await client.request(request.method, url, content=body, headers=headers)
        except httpx.HTTPError:
            return await self.unavailable(scope, receive, send)
        response_headers = dict(PRIVATE_HEADERS)
        for key in ("content-type", "content-disposition", "content-range", "accept-ranges"):
            if key in upstream.headers:
                response_headers[key] = upstream.headers[key]
        location = upstream.headers.get("location")
        if location:
            redirect = urlsplit(location)
            redirect_path = unquote(redirect.path)
            if (
                (redirect.netloc and (redirect.scheme + "://" + redirect.netloc) != UPSTREAM)
                or "\\" in redirect_path
                or any(segment in {".", ".."} for segment in redirect_path.split("/"))
            ):
                return await Response(status_code=502, headers=PRIVATE_HEADERS)(scope, receive, send)
            response_headers["Location"] = PREFIX + "/" + redirect.path.lstrip("/")
            if redirect.query:
                response_headers["Location"] += "?" + redirect.query
        response_headers["Content-Security-Policy"] = (
            "default-src 'self' data: blob:; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; "
            "font-src 'self' data:; connect-src " + config["public_origin"] + PREFIX + "/ blob:; "
            "object-src 'none'; base-uri 'self'; form-action 'none'; "
            "frame-ancestors 'self'; worker-src 'none'"
        )
        response = Response(upstream.content, status_code=upstream.status_code, headers=response_headers)
        return await response(scope, receive, send)

    async def admin_document(self, scope, receive, send):
        messages = []

        async def collect(message):
            messages.append(message)

        document_scope = {**scope, "headers": [
            (key, value) for key, value in scope.get("headers", [])
            if key.lower() not in {b"if-none-match", b"if-modified-since"}
        ]}
        await self.app(document_scope, receive, collect)
        start = next((message for message in messages if message["type"] == "http.response.start"), None)
        headers = dict(start.get("headers", [])) if start else {}
        if start and start["status"] == 200 and b"text/html" in headers.get(b"content-type", b""):
            body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
            body = body.replace(b"<body>", b"<body>" + LAUNCHER.encode("utf-8"), 1)
            headers.pop(b"etag", None)
            headers.pop(b"last-modified", None)
            headers[b"cache-control"] = b"no-store"
            headers[b"vary"] = b"Cookie"
            headers[b"content-length"] = str(len(body)).encode("ascii")
            await send({**start, "headers": list(headers.items())})
            await send({"type": "http.response.body", "body": body})
        else:
            for message in messages:
                await send(message)

    async def unavailable(self, scope, receive, send):
        response = HTMLResponse(
            '<!doctype html><html lang="ru"><meta charset="utf-8"><title>Предпросмотр</title>'
            '<body><h1>Предпросмотр временно недоступен</h1><p>Основной сайт работает отдельно.</p>'
            '<a href="/admin">Вернуться в админку</a></body></html>',
            status_code=503, headers=PRIVATE_HEADERS,
        )
        return await response(scope, receive, send)


def install_admin_preview(app, *, config_path=None):
    path = config_path or os.environ.get("ADMIN_PREVIEW_CONFIG")
    if path:
        app.add_middleware(AdminPreviewGateway, config_path=path)
