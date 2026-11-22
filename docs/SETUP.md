# Запуск, проверка и выпуск релиза

## Локальный запуск

Требуются Python 3.11, PostgreSQL для production-сценариев и Node.js для сборки фронтенда.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
Copy-Item docs\env.example .env
.\.venv\Scripts\python.exe scripts\bootstrap_local_sqlite.py --rebuild --seed
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

Флаг `--no-access-log` обязателен: стандартный access log Uvicorn включает query-параметры OAuth callback, в том числе одноразовый code.

Локальная SQLite собирается напрямую из актуальных SQLAlchemy-моделей и отмечается текущей Alembic-ревизией. Исторические миграции проекта рассчитаны на PostgreSQL, поэтому их не нужно прогонять поверх `clanwar_local.db`. При повторном запуске bootstrap сначала полностью создаёт новый временный файл, сохраняет предыдущую базу как `clanwar_local.backup.db` и только затем заменяет рабочую базу.

В отдельном окне для разработки фронтенда:

```powershell
cd frontend
npm install
npm run dev
```

API доступен на `http://localhost:8000`, development frontend обычно на `http://localhost:3000`.

### Визуальная обратная связь через Agentation

Agentation доступен только в development-сборке и не попадает в production-бандл. Перед визуальной сессией запустите локальный HTTP-сервис в ещё одном окне:

```powershell
cd frontend
npm run agentation
```

Toolbar появится справа снизу на `http://localhost:3000`. Аннотации хранятся локально и синхронизируются через `http://localhost:4747`.

Для прямого доступа Codex к аннотациям MCP настраивается один раз:

```powershell
codex mcp add agentation -- npx.cmd -y agentation-mcp server --mcp-only --http-url http://localhost:4747
```

После изменения списка MCP откройте новую сессию Codex. Сам frontend продолжает работать и без MCP: аннотации можно скопировать из toolbar вручную.

## Проверки перед релизом

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app alembic
cd frontend
npm run build
```

`npm run build` сначала проверяет локализацию, затем собирает `frontend/dist`. В релизе эта папка обязательна: именно она содержит `index.html`, который раздает FastAPI.

## Миграции

Миграции являются единственным способом изменения схемы production-базы PostgreSQL. Для локальной SQLite используется описанный выше bootstrap, потому что она служит только средой разработки и не хранит историю сезона.

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Нельзя запускать на production `alembic downgrade` или удалять таблицы без отдельного плана восстановления.

## Подготовка архива

Перед упаковкой закройте `.env`, базы, логи, replay и пользовательские загрузки от попадания в архив. Скрипт уже исключает их и сохраняет только две последние локальные архивные версии.

```powershell
cd deploy
.\package-release.ps1 -ReleaseName clanwar-YYYYMMDD-vN
```

Проверьте архив:

```powershell
tar -tf .\clanwar-YYYYMMDD-vN.tar.gz | Select-String 'frontend/dist/index.html'
tar -tf .\clanwar-YYYYMMDD-vN.tar.gz | Select-String '(^|/)\.env'
```

Первая команда обязана найти `frontend/dist/index.html`. Вторая не должна ничего вывести.

## Проверка сервера

Скрипты в `deploy/` приведены как шаблоны для самостоятельного развёртывания. Для своего сервера нужно указать собственный домен, пользователя, пути и ключи.

Для ручной серверной диагностики:

```bash
curl -fsSI http://127.0.0.1:8000/
curl -fsS http://127.0.0.1:8000/health/ready
systemctl is-active clanwar
systemctl is-active clanwar-worker
```

Проверка двигателя матчей и безопасная догрузка доступной истории:

```bash
journalctl -u clanwar-worker -n 100 --no-pager
cd /home/clanwar/apps/clanwar/current
.venv/bin/python scripts/backfill_matches.py --days 3650 --per-mode 500
```

В журнале успешного цикла должны быть явно указаны источник, число
просмотренных replay и число новых матчей. Невалидный ответ источника считается
ошибкой worker, а не успешной синхронизацией с нулевым результатом. Команда
backfill не двигает рабочий курсор и идемпотентна по `match_id`. Без Bearer-токена
она охватывает окно, опубликованное в HTML-архиве BFME Arena; полный произвольный
диапазон дат требует `LADDER_PUBLIC_API_ENABLED=true` и токен только в серверном
`.env`.

После успешной авторизации через BFME Arena приложение создаёт одну
идемпотентную задачу в `arena_match_backfill_jobs` и сразу запускает персональную
догрузку. Она проходит все страницы HTML-архива по текущему нику Arena, не
двигает курсор общей синхронизации и повторно не создаётся при следующих входах.
Если Arena временно недоступна или web-процесс перезапущен, campaign worker
подхватывает незавершённую задачу и повторяет её с увеличивающейся задержкой.
Параметры `ARENA_BACKFILL_JOBS_PER_CYCLE`, `ARENA_BACKFILL_MAX_PAGES` и
`ARENA_BACKFILL_RETRY_SECONDS` ограничивают нагрузку и настраиваются без
изменения кода.

## Переменные окружения

Пример переменных окружения находится в [env.example](env.example). Для Discord есть отдельный [пример настроек](discord.env.example). Настоящие ключи и пароли нужно хранить вне Git.

## Резервное копирование

В `deploy/backup` находятся unit, timer и скрипт проверочного восстановления. Backup включает PostgreSQL dump, uploads, replay, превью карт и SHA-256 manifest. Восстановление запускается только в отдельную тестовую базу; production-база не должна передаваться ему как restore-target.

## Что делать при проблеме

1. Проверьте `systemctl status clanwar clanwar-worker`.
2. Проверьте `journalctl -u clanwar -u clanwar-worker -n 200 --no-pager`.
3. Проверьте `/health/live` и `/health/ready`.
4. Если readiness не проходит после нового релиза, release-скрипт должен вернуть предыдущую версию автоматически. Не удаляйте релизы вручную до выяснения причины.
