"""Подтверждение полного обхода Арены после успешного сохранения всех ответов.

Создаётся загрузчиком, а не из пользовательского запроса. После перезапуска
несохранённое подтверждение теряется: нужен новый обход, а не доверие к heartbeat.
"""

from dataclasses import dataclass
from datetime import datetime

from app.services.campaign_cycle_service import _utc


@dataclass(frozen=True)
class ArenaReplayScan:
    covered_start: datetime
    covered_end: datetime
    source_cursor: str
    replay_ids: frozenset[str] = frozenset()

    def __post_init__(self):
        for name in ('covered_start', 'covered_end'):
            object.__setattr__(self, name, _utc(getattr(self, name)))
        if self.covered_start >= self.covered_end:
            raise ValueError('Начало проверки должно быть раньше окончания')
        if not isinstance(self.source_cursor, str) or not self.source_cursor.strip() or len(self.source_cursor) > 500:
            raise ValueError('Необходим идентификатор завершённой загрузки')
        if not isinstance(self.replay_ids, frozenset) or any(
                not isinstance(value, str) or not value.strip() for value in self.replay_ids):
            raise ValueError('Необходим неизменяемый набор идентификаторов реплеев')

    def covers(self, *, start, deadline, now):
        return self.covered_start <= _utc(start) and _utc(deadline) <= self.covered_end <= _utc(now)
