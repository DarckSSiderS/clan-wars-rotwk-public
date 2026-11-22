"""Безопасно собрать локальную SQLite из актуальных SQLAlchemy-моделей."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.campaign_rules import default_campaign_rule_values
from app.database import Base
from app.models import CampaignRuleSet  # noqa: F401
import app.models  # noqa: F401


def current_head() -> str:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if not head:
        raise RuntimeError("В Alembic не найдена текущая вершина миграций")
    return head


def _stamp_head(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE alembic_version ("
                "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": current_head()},
        )


def _seed_local_data(session) -> None:
    from app.services.bootstrap_service import (
        ensure_admin_test_clan,
        ensure_campaign_rules,
        ensure_default_admin,
        ensure_progression_content,
        ensure_shop_content,
    )

    session.add(
        CampaignRuleSet(
            version=1,
            values=default_campaign_rule_values(),
            is_active=True,
            reason="local_sqlite_bootstrap",
        )
    )
    session.commit()
    ensure_default_admin(session)
    ensure_progression_content(session)
    ensure_shop_content(session)
    ensure_campaign_rules(session)
    ensure_admin_test_clan(session)


def build_local_sqlite_database(
    database_path: Path,
    *,
    seed: bool,
) -> Path:
    database_path = Path(database_path).resolve()
    if database_path.exists():
        raise FileExistsError(f"Файл уже существует: {database_path}")
    database_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    try:
        Base.metadata.create_all(engine)
        _stamp_head(engine)
        if seed:
            local_session = sessionmaker(bind=engine)()
            try:
                _seed_local_data(local_session)
            finally:
                local_session.close()
    except Exception:
        engine.dispose()
        database_path.unlink(missing_ok=True)
        raise
    engine.dispose()
    return database_path


def rebuild_configured_sqlite(*, seed: bool) -> tuple[Path, Path | None]:
    url = make_url(settings.DATABASE_URL)
    if not url.drivername.startswith("sqlite") or not url.database:
        raise RuntimeError(
            "Команда предназначена только для локальной SQLite и не работает с PostgreSQL"
        )

    configured_path = Path(url.database)
    target = (
        configured_path
        if configured_path.is_absolute()
        else PROJECT_ROOT / configured_path
    ).resolve()
    if PROJECT_ROOT not in target.parents:
        raise RuntimeError(f"Локальная база находится вне проекта: {target}")

    temporary = target.with_name(f"{target.stem}.rebuild{target.suffix}")
    backup = target.with_name(f"{target.stem}.backup{target.suffix}")
    temporary.unlink(missing_ok=True)
    build_local_sqlite_database(temporary, seed=seed)

    backup_path = None
    if target.exists():
        shutil.copy2(target, backup)
        backup_path = backup
    os.replace(temporary, target)
    return target, backup_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Пересобрать локальную SQLite по актуальным моделям и отметить её "
            "текущей Alembic-ревизией."
        )
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Подтвердить замену настроенной локальной SQLite.",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Добавить карту, администратора и тестовый контент.",
    )
    args = parser.parse_args()
    if not args.rebuild:
        parser.error("Для выполнения явно укажите --rebuild")

    target, backup = rebuild_configured_sqlite(seed=args.seed)
    print(f"Локальная база готова: {target}")
    print(f"Alembic revision: {current_head()}")
    if backup:
        print(f"Предыдущая база сохранена: {backup}")


if __name__ == "__main__":
    main()
