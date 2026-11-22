#!/usr/bin/env python3
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.database import SessionLocal
from app.models.territory import Territory
from app.services.territory_adjacency_service import (
    _flatten_svg_path,
    infer_svg_adjacency,
)


def territory_boxes(svg_path, interactive_only=False):
    root = ET.parse(svg_path).getroot()
    boxes = set()
    seen_path_data = set()
    for element in root.iter():
        if not element.tag.endswith("path"):
            continue
        if interactive_only and "interactive-region" not in element.attrib.get("class", ""):
            continue
        path_data = (element.attrib.get("d") or "").strip()
        if not path_data or path_data in seen_path_data:
            continue
        seen_path_data.add(path_data)
        points = _flatten_svg_path(path_data)
        boxes.add(
            tuple(
                round(value, 3)
                for value in (
                    min(point[0] for point in points),
                    min(point[1] for point in points),
                    max(point[0] for point in points),
                    max(point[1] for point in points),
                )
            )
        )
    return boxes


def validate_routes():
    svg_path = ROOT / "frontend" / "public" / "map-interactive.svg"
    base_map_path = ROOT / "frontend" / "public" / "map.svg"
    expected, _ = infer_svg_adjacency(svg_path)
    errors = []

    base_boxes = territory_boxes(base_map_path)
    interactive_boxes = territory_boxes(svg_path, interactive_only=True)
    if base_boxes != interactive_boxes:
        errors.append(
            "Base and interactive maps differ: "
            f"missing overlays={len(base_boxes - interactive_boxes)}, "
            f"unknown overlays={len(interactive_boxes - base_boxes)}"
        )

    with SessionLocal() as db:
        territories = db.query(Territory).order_by(Territory.id).all()
        by_id = {territory.id: territory for territory in territories}
        by_name = {territory.name: territory for territory in territories}

        if len(territories) != len(by_name):
            errors.append("Database contains duplicate territory names")
        if set(by_name) != set(expected):
            errors.append(
                "SVG/database names differ: "
                f"only SVG={sorted(set(expected) - set(by_name))}, "
                f"only database={sorted(set(by_name) - set(expected))}"
            )

        for territory in territories:
            neighbor_ids = territory.adjacent_territory_ids or []
            if territory.id in neighbor_ids:
                errors.append(f"{territory.name} references itself")
            if len(neighbor_ids) != len(set(neighbor_ids)):
                errors.append(f"{territory.name} contains duplicate routes")
            unknown_ids = sorted(set(neighbor_ids) - set(by_id))
            if unknown_ids:
                errors.append(f"{territory.name} references unknown IDs {unknown_ids}")

            actual_names = {by_id[item].name for item in neighbor_ids if item in by_id}
            if actual_names != expected.get(territory.name, set()):
                errors.append(
                    f"{territory.name} routes differ: "
                    f"database={sorted(actual_names)}, SVG={sorted(expected.get(territory.name, set()))}"
                )

            for neighbor_id in neighbor_ids:
                if neighbor_id in by_id and territory.id not in (
                    by_id[neighbor_id].adjacent_territory_ids or []
                ):
                    errors.append(
                        f"Asymmetric route: {territory.name} -> {by_id[neighbor_id].name}"
                    )

            if territory.is_playable and not neighbor_ids:
                errors.append(f"Playable territory {territory.name} has no land routes")
            if territory.has_port and not territory.is_coastal:
                errors.append(f"Port {territory.name} is not marked coastal")

        tol_falas = by_name.get("Тол-Фалас")
        if not tol_falas or tol_falas.is_playable:
            errors.append("Tol-Falas must exist and remain unavailable")

        ports = [territory for territory in territories if territory.has_port]
        coastal_targets = [
            territory
            for territory in territories
            if territory.is_coastal and territory.is_playable
        ]
        for port in ports:
            if not any(target.id != port.id for target in coastal_targets):
                errors.append(f"Port {port.name} has no sea targets")

    if errors:
        print("Territory route validation failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    edge_count = sum(len(items) for items in expected.values()) // 2
    print(
        f"OK: {len(expected)} territories, {edge_count} symmetric land routes, "
        f"{len(ports)} ports, {len(coastal_targets)} playable coastal targets"
    )


if __name__ == "__main__":
    validate_routes()
