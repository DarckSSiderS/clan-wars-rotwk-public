import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import inspect, text

sys.path.insert(0, str(Path.cwd()))
shared_env = Path("/home/clanwar/apps/clanwar/shared/.env")
if shared_env.exists():
    load_dotenv(shared_env)

from app.database import engine


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def main() -> None:
    inspector = inspect(engine)
    report = {
        "database": engine.dialect.name,
        "size_bytes": None,
        "tables": {},
        "orphaned_foreign_keys": [],
        "case_insensitive_duplicate_usernames": [],
        "expired_open_market_offers": 0,
        "overdue_traveling_caravans": 0,
    }
    with engine.connect() as connection:
        if engine.dialect.name == "postgresql":
            report["size_bytes"] = connection.execute(
                text("SELECT pg_database_size(current_database())")
            ).scalar()

        table_names = inspector.get_table_names()
        for table_name in sorted(table_names):
            report["tables"][table_name] = connection.execute(
                text(f"SELECT COUNT(*) FROM {quote(table_name)}")
            ).scalar()
            for foreign_key in inspector.get_foreign_keys(table_name):
                constrained = foreign_key.get("constrained_columns") or []
                referred = foreign_key.get("referred_columns") or []
                parent_table = foreign_key.get("referred_table")
                if len(constrained) != 1 or len(referred) != 1 or not parent_table:
                    continue
                child_column = constrained[0]
                parent_column = referred[0]
                orphan_count = connection.execute(
                    text(
                        f"SELECT COUNT(*) FROM {quote(table_name)} child "
                        f"LEFT JOIN {quote(parent_table)} parent "
                        f"ON child.{quote(child_column)} = parent.{quote(parent_column)} "
                        f"WHERE child.{quote(child_column)} IS NOT NULL "
                        f"AND parent.{quote(parent_column)} IS NULL"
                    )
                ).scalar()
                if orphan_count:
                    report["orphaned_foreign_keys"].append(
                        {
                            "table": table_name,
                            "column": child_column,
                            "parent_table": parent_table,
                            "count": orphan_count,
                        }
                    )

        if "users" in table_names:
            duplicate_rows = connection.execute(
                text(
                    "SELECT lower(username) AS username, COUNT(*) AS count "
                    "FROM users GROUP BY lower(username) HAVING COUNT(*) > 1"
                )
            ).mappings()
            report["case_insensitive_duplicate_usernames"] = [
                dict(row) for row in duplicate_rows
            ]
        if "market_offers" in table_names:
            report["expired_open_market_offers"] = connection.execute(
                text(
                    "SELECT COUNT(*) FROM market_offers "
                    "WHERE status = 'open' AND expires_at <= now()"
                )
            ).scalar()
        if "trade_caravans" in table_names:
            report["overdue_traveling_caravans"] = connection.execute(
                text(
                    "SELECT COUNT(*) FROM trade_caravans "
                    "WHERE status = 'traveling' AND eta <= now()"
                )
            ).scalar()

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
