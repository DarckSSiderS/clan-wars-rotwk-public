import argparse
import json
from collections.abc import Iterable

from sqlalchemy import MetaData, create_engine, inspect, select, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql.sqltypes import JSON


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-url", required=True)
    parser.add_argument("--postgres-url", required=True)
    parser.add_argument("--batch-size", type=int, default=500)
    return parser.parse_args()


def chunks(rows: list[dict], size: int) -> Iterable[list[dict]]:
    for index in range(0, len(rows), size):
        yield rows[index:index + size]


def convert_value(value, target_type):
    if value is None:
        return None
    if isinstance(target_type, (JSON, ARRAY)) and isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if parsed is not None else []
        except json.JSONDecodeError:
            return [value] if isinstance(target_type, ARRAY) else value
    return value


def reset_sequence(connection, table_name: str, column_name: str) -> None:
    sequence = connection.execute(
        text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
        {"table_name": table_name, "column_name": column_name},
    ).scalar()
    if not sequence:
        return
    maximum = connection.execute(
        text(f'SELECT MAX("{column_name}") FROM "{table_name}"')
    ).scalar()
    if maximum is not None:
        connection.execute(
            text("SELECT setval(:sequence, :maximum, true)"),
            {"sequence": sequence, "maximum": maximum},
        )


def main() -> None:
    args = parse_args()
    source_engine = create_engine(args.sqlite_url)
    target_engine = create_engine(args.postgres_url)
    source_meta = MetaData()
    target_meta = MetaData()
    source_meta.reflect(bind=source_engine)
    target_meta.reflect(bind=target_engine)

    excluded = {"alembic_version", "worker_heartbeats"}
    ordered_names = [
        table.name
        for table in target_meta.sorted_tables
        if table.name in source_meta.tables and table.name not in excluded
    ]

    with target_engine.begin() as target:
        for table_name in reversed(ordered_names):
            target.execute(target_meta.tables[table_name].delete())

        for table_name in ordered_names:
            source_table = source_meta.tables[table_name]
            target_table = target_meta.tables[table_name]
            common_columns = [
                column.name
                for column in target_table.columns
                if column.name in source_table.columns
            ]
            with source_engine.connect() as source:
                source_rows = source.execute(
                    select(*(source_table.c[name] for name in common_columns))
                ).mappings().all()

            converted_rows = [
                {
                    name: convert_value(row[name], target_table.c[name].type)
                    for name in common_columns
                }
                for row in source_rows
            ]
            for batch in chunks(converted_rows, args.batch_size):
                target.execute(target_table.insert(), batch)
            print(f"{table_name}: {len(converted_rows)}")

        for table_name in ordered_names:
            table = target_meta.tables[table_name]
            for column in table.primary_key.columns:
                if column.name == "id":
                    reset_sequence(target, table_name, column.name)

    source_counts = {
        name: inspect(source_engine).get_table_names().count(name)
        for name in ordered_names
    }
    if not all(source_counts.values()):
        raise RuntimeError("Source schema changed during migration")


if __name__ == "__main__":
    main()
