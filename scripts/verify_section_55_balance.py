"""Verify the complete, deterministic acceptance contract for document section 55."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.section_55_balance_service import build_section_55_balance_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Проверить все числовые требования раздела 55 без доступа к БД.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Напечатать полный машинный отчёт JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_section_55_balance_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        status = "PASS" if report["passed"] else "FAIL"
        print(f"Section 55 economy balance: {status}")
        for check in report["checks"]:
            marker = "PASS" if check["passed"] else "FAIL"
            print(f"[{marker}] {check['code']}: {check['actual']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
