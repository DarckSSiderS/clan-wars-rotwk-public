from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import mimetypes
import re
from time import perf_counter
from uuid import uuid4
from pathlib import Path
from contextlib import asynccontextmanager

from app.config import settings
from app.api.v1 import admin, admin_balance, admin_campaign_rules, admin_clan_warfare, oauth, users, clans, wars, shop, achievements, localization, scheduler, quests, streams, territories, statistics, campaign, notifications, diplomacy, messaging, realtime, presence, feedback
from app.api import health
from app.api.v1 import discord as discord_api
from app.api.v1 import cycle_admin_economy
from app.api.v1 import cycle_clan_history
from app.services.realtime_service import realtime_hub


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        request_path = scope.get("path", "")
        if request_path == "/api" or request_path.startswith("/api/"):
            raise StarletteHTTPException(status_code=404)
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if (
                exc.status_code == 404
                and not path.startswith('assets/')
                and Path(path).suffix.lower() not in {'.js', '.css', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.woff', '.woff2', '.ico'}
                and (Path(self.directory) / "index.html").exists()
            ):
                return await super().get_response("index.html", scope)
            raise


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Запуск приложения ClanWar")
    await realtime_hub.startup()
    try:
        yield
    finally:
        await realtime_hub.shutdown()
        logger.info("Остановка приложения ClanWar")


# Создаем приложение FastAPI
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_context(request, call_next):
    supplied_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        supplied_request_id
        if REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
        else uuid4().hex
    )
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        raise

    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed request_id=%s method=%s path=%s status=%s duration_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

# Подключаем API роуты
app.include_router(oauth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(clans.router, prefix="/api/v1")
app.include_router(wars.router, prefix="/api/v1")
app.include_router(shop.router, prefix="/api/v1")
app.include_router(achievements.router, prefix="/api/v1")
app.include_router(localization.router, prefix="/api/v1/localization")

app.include_router(scheduler.router, prefix="/api/v1")
app.include_router(quests.router, prefix="/api/v1")
app.include_router(streams.router, prefix="/api/v1/streams")
app.include_router(territories.router, prefix="/api/v1/territories")
app.include_router(statistics.router, prefix="/api/v1")
app.include_router(campaign.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(diplomacy.router, prefix="/api/v1")
app.include_router(messaging.router, prefix="/api/v1")
app.include_router(realtime.router, prefix="/api/v1")
app.include_router(presence.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")
app.include_router(feedback.admin_router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(cycle_admin_economy.router, prefix="/api/v1")
app.include_router(cycle_clan_history.router, prefix="/api/v1")
app.include_router(admin_balance.router, prefix="/api/v1")
app.include_router(admin_campaign_rules.router, prefix="/api/v1")
app.include_router(admin_clan_warfare.router, prefix="/api/v1")
app.include_router(health.router)
app.include_router(discord_api.router, prefix="/api/v1")

upload_dir = Path(settings.UPLOAD_DIR)
upload_dir.mkdir(parents=True, exist_ok=True)
mimetypes.add_type("image/webp", ".webp")
app.mount("/images", StaticFiles(directory=str(upload_dir)), name="images")

frontend_dist = Path("frontend/dist")
frontend_public = Path("frontend/public")
frontend_dir = frontend_dist if (frontend_dist / "index.html").exists() else frontend_public

# Подключаем статические файлы ПОСЛЕ API роутов
from app.admin_preview_gateway import install_admin_preview
install_admin_preview(app)
app.mount("/", SPAStaticFiles(directory=str(frontend_dir), html=True), name="frontend")

# Добавляем middleware для заголовков кэширования
@app.middleware("http")
async def add_cache_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if response.status_code == 200 and re.fullmatch(r'/assets/[^/]+-[A-Za-z0-9_-]{6,}\.(?:js|css|woff2)', path):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    elif response.status_code == 200 and 'text/html' in response.headers.get('content-type', ''):
        response.headers['Cache-Control'] = 'no-cache'
    is_map_preview = request.url.path.startswith(
        "/api/v1/statistics/map-previews/",
    )
    is_archive_map = re.fullmatch(r'/api/v1/campaign/archives/[1-9]\d*/map\.svg', path) is not None
    if (
        request.url.path.startswith("/api/")
        and not is_map_preview
        and not is_archive_map
    ) or request.url.path.startswith("/images/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
