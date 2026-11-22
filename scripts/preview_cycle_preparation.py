"""Проверяет подготовку нового режима только на ранее созданной копии внутри .tmp."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    args = parser.parse_args()
    path = args.database.resolve()
    manifest = path.parent / 'report.json'
    if (not path.is_relative_to((ROOT / '.tmp').resolve()) or path.name != 'rehearsal.db'
            or not path.is_file() or not manifest.is_file()):
        raise ValueError('Разрешена только изолированная база rehearsal.db с отчётом репетиции')
    previous = json.loads(manifest.read_text(encoding='utf-8'))
    if previous.get('copy') != str(path) or previous.get('source_opened_read_only') is not True:
        raise ValueError('Копия не соответствует отчёту миграций')
    from app.services.cycle_launch_preflight import preview_preparation
    engine = create_engine('sqlite:///' + path.as_posix())
    try:
        with sessionmaker(bind=engine, autoflush=False)() as db:
            report = preview_preparation(db, now=datetime.now(timezone.utc))
            db.rollback()
        output = path.parent / 'preparation-report.json'
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
