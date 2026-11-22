# Импорт матчей BFME Arena

Production-импорт выполняет `BFMELadderService` через campaign worker. При
настроенном `LADDER_PUBLIC_API_TOKEN` используется фильтрованный JSON API. Без
токена сервис читает серверный HTML-архив BFME Arena, валидирует карточки и
импортирует только завершённые рейтинговые матчи RotWK для `Patch 2.02` и
`Ennorath` в режимах `1v1`-`4v4`.

Устаревший `/api/replays` больше не является рабочим источником и не должен
использоваться для production-синхронизации. Старые `import_rotwk_matches_*.py`
сохранены только как исторические диагностические инструменты.

## Backfill доступного архива

Из корня проекта:

```bash
.venv/bin/python scripts/backfill_matches.py --days 3650 --per-mode 500
```

Для истории конкретного игрока:

```bash
.venv/bin/python scripts/backfill_matches.py --player Nickname --days 3650
```

Команда не двигает рабочий курсор и безопасна для повторного запуска: replay
дедуплицируются по `match_id`. HTML-источник охватывает окно, опубликованное на
странице архива. Для гарантированного полного диапазона дат требуется
`LADDER_PUBLIC_API_ENABLED=true` и Bearer-токен только в серверном `.env`.

## Проверка

```bash
systemctl is-active clanwar-worker
journalctl -u clanwar-worker -n 100 --no-pager
```

Успешный цикл пишет источник, число просмотренных и импортированных replay.
Ошибка формата или недоступность источника завершают цикл ошибкой и попадают в
`worker_heartbeats.last_error`; HTTP 200 с невалидным содержимым успехом не
считается.
