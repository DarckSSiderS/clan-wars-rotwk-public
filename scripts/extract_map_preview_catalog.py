"""Извлекает компактный каталог изображений карт из архивного ответа BFME Ladder."""

import argparse
import json
import re
from pathlib import Path


ENTRY_PATTERN = re.compile(
    r'"MapId":"(?P<map_id>[^"]+)",'
    r'"MapName":"(?P<map_name>[^"]*)",'
    r'"MapPreviewSource":"(?P<source>[^"]+)"'
)


def extract_catalog(source_path: Path) -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    tail = ""
    with source_path.open("r", encoding="utf-8") as source_file:
        while chunk := source_file.read(1024 * 1024):
            text = tail + chunk
            for match in ENTRY_PATTERN.finditer(text):
                catalog[match.group("map_id")] = {
                    "name": match.group("map_name"),
                    "source": match.group("source"),
                }
            tail = text[-4096:]
    return catalog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    catalog = extract_catalog(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Сохранено карт: {len(catalog)}")


if __name__ == "__main__":
    main()
