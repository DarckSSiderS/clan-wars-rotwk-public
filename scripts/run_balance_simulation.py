"""Run the deterministic, read-only campaign balance simulation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal
from app.services.balance_simulation_catalog import BalanceSimulationCatalogLoader
from app.services.balance_simulation_report import write_simulation_reports
from app.services.balance_simulation_service import BalanceSimulationService


def _enable_read_only(db) -> None:
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(text("SET TRANSACTION READ ONLY"))
    elif dialect == "sqlite":
        db.execute(text("PRAGMA query_only = ON"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Смоделировать экономику кампании без изменения базы и создать "
            "детерминированные JSON/Markdown-отчёты."
        )
    )
    parser.add_argument(
        "--days",
        type=int,
        choices=(7, 14, 30),
        default=30,
        help="Горизонт симуляции, по умолчанию 30 суток.",
    )
    parser.add_argument(
        "--rule-version",
        type=int,
        default=None,
        help="Версия правил; по умолчанию используется активная.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "docs" / "balance" / "reports",
        help="Каталог готовых отчётов.",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Создать только машинный JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = SessionLocal()
    try:
        _enable_read_only(db)
        catalog = BalanceSimulationCatalogLoader().load(
            db,
            rule_version=args.rule_version,
        )
        result = BalanceSimulationService().run(catalog, days=args.days)
        db.rollback()
    except (LookupError, ValueError, RuntimeError) as error:
        db.rollback()
        print(f"Симуляция не выполнена: {error}", file=sys.stderr)
        return 2
    finally:
        db.close()

    json_path, markdown_path = write_simulation_reports(
        result,
        args.output_dir,
        json_only=args.json_only,
    )
    print(f"JSON: {json_path}")
    if markdown_path is not None:
        print(f"Markdown: {markdown_path}")
    print(
        f"Сценариев: {len(result['scenarios'])}; "
        f"сигналов: {len(result['signals'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
