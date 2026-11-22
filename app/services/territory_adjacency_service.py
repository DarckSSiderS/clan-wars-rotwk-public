import hashlib
import json
import math
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from app.models.territory import Territory
from app.core.territory_development import initial_military_level


NUMBER_OR_COMMAND = re.compile(
    r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?"
)
SUPPORTED_COMMANDS = {"M", "L", "H", "V", "C", "S", "Z"}
DEFAULT_BORDER_TOLERANCE = 25.0
REQUIRED_ADJACENCY_EDGES = {
    frozenset(("Центральный Итилиен", "Минас Моргул")),
}
FORBIDDEN_ADJACENCY_EDGES = {
    frozenset(("Удун", "Минас Моргул")),
}
EXPECTED_ADJACENCY_FINGERPRINT = (
    "ae4081892911895a47311b52687f639f72e18e416c880e3ec0b7840fd997b6d9"
)


def _cubic_point(start, control_a, control_b, end, ratio):
    inverse = 1.0 - ratio
    return (
        inverse**3 * start[0]
        + 3 * inverse**2 * ratio * control_a[0]
        + 3 * inverse * ratio**2 * control_b[0]
        + ratio**3 * end[0],
        inverse**3 * start[1]
        + 3 * inverse**2 * ratio * control_a[1]
        + 3 * inverse * ratio**2 * control_b[1]
        + ratio**3 * end[1],
    )


def _flatten_svg_path(path_data: str, cubic_steps: int = 14):
    tokens = NUMBER_OR_COMMAND.findall(path_data)
    points = []
    cursor = (0.0, 0.0)
    subpath_start = cursor
    command = None
    previous_command = None
    previous_cubic_control = None
    index = 0

    def read_number():
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    def read_point(relative):
        x, y = read_number(), read_number()
        if relative:
            return cursor[0] + x, cursor[1] + y
        return x, y

    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            command = token
            index += 1
        if command is None or command.upper() not in SUPPORTED_COMMANDS:
            raise ValueError(f"Unsupported SVG command: {command}")

        upper = command.upper()
        relative = command.islower()
        if upper == "Z":
            if not points or points[-1] != subpath_start:
                points.append(subpath_start)
            cursor = subpath_start
            previous_cubic_control = None
            previous_command = upper
            command = None
            continue

        if upper == "M":
            cursor = read_point(relative)
            subpath_start = cursor
            points.append(cursor)
            previous_cubic_control = None
            previous_command = upper
            command = "l" if relative else "L"
            continue

        if upper == "L":
            cursor = read_point(relative)
            points.append(cursor)
            previous_cubic_control = None
        elif upper == "H":
            x = read_number() + (cursor[0] if relative else 0.0)
            cursor = (x, cursor[1])
            points.append(cursor)
            previous_cubic_control = None
        elif upper == "V":
            y = read_number() + (cursor[1] if relative else 0.0)
            cursor = (cursor[0], y)
            points.append(cursor)
            previous_cubic_control = None
        elif upper == "C":
            start = cursor
            control_a = read_point(relative)
            control_b = read_point(relative)
            end = read_point(relative)
            for step in range(1, cubic_steps + 1):
                points.append(
                    _cubic_point(start, control_a, control_b, end, step / cubic_steps)
                )
            cursor = end
            previous_cubic_control = control_b
        elif upper == "S":
            start = cursor
            if previous_command in {"C", "S"} and previous_cubic_control:
                control_a = (
                    2 * cursor[0] - previous_cubic_control[0],
                    2 * cursor[1] - previous_cubic_control[1],
                )
            else:
                control_a = cursor
            control_b = read_point(relative)
            end = read_point(relative)
            for step in range(1, cubic_steps + 1):
                points.append(
                    _cubic_point(start, control_a, control_b, end, step / cubic_steps)
                )
            cursor = end
            previous_cubic_control = control_b

        previous_command = upper

    return points


def _point_segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == 0 and dy == 0:
        return math.dist(point, start)
    ratio = (
        (point[0] - start[0]) * dx + (point[1] - start[1]) * dy
    ) / (dx * dx + dy * dy)
    ratio = max(0.0, min(1.0, ratio))
    projection = start[0] + ratio * dx, start[1] + ratio * dy
    return math.dist(point, projection)


def _orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(a, b, c, d):
    first = _orientation(a, b, c)
    second = _orientation(a, b, d)
    third = _orientation(c, d, a)
    fourth = _orientation(c, d, b)
    epsilon = 1e-7
    return (
        (first > epsilon and second < -epsilon or first < -epsilon and second > epsilon)
        and (third > epsilon and fourth < -epsilon or third < -epsilon and fourth > epsilon)
    )


def _segment_distance(a, b, c, d):
    if _segments_intersect(a, b, c, d):
        return 0.0
    return min(
        _point_segment_distance(a, c, d),
        _point_segment_distance(b, c, d),
        _point_segment_distance(c, a, b),
        _point_segment_distance(d, a, b),
    )


def _path_distance(first, second, cutoff):
    first_box = (
        min(point[0] for point in first),
        min(point[1] for point in first),
        max(point[0] for point in first),
        max(point[1] for point in first),
    )
    second_box = (
        min(point[0] for point in second),
        min(point[1] for point in second),
        max(point[0] for point in second),
        max(point[1] for point in second),
    )
    if (
        first_box[2] + cutoff < second_box[0]
        or second_box[2] + cutoff < first_box[0]
        or first_box[3] + cutoff < second_box[1]
        or second_box[3] + cutoff < first_box[1]
    ):
        return math.inf

    shortest = math.inf
    for first_start, first_end in zip(first, first[1:]):
        segment_box = (
            min(first_start[0], first_end[0]) - cutoff,
            min(first_start[1], first_end[1]) - cutoff,
            max(first_start[0], first_end[0]) + cutoff,
            max(first_start[1], first_end[1]) + cutoff,
        )
        for second_start, second_end in zip(second, second[1:]):
            if (
                max(second_start[0], second_end[0]) < segment_box[0]
                or min(second_start[0], second_end[0]) > segment_box[2]
                or max(second_start[1], second_end[1]) < segment_box[1]
                or min(second_start[1], second_end[1]) > segment_box[3]
            ):
                continue
            shortest = min(
                shortest,
                _segment_distance(first_start, first_end, second_start, second_end),
            )
            if shortest <= 1e-7:
                return 0.0
    return shortest


def infer_svg_adjacency(svg_path: Path, tolerance=DEFAULT_BORDER_TOLERANCE):
    root = ET.parse(svg_path).getroot()
    outlines = {}
    seen_path_data = set()
    for element in root.iter():
        if not element.tag.endswith("path"):
            continue
        if "interactive-region" not in element.attrib.get("class", ""):
            continue
        name = (element.attrib.get("data-name") or "").strip()
        path_data = (element.attrib.get("d") or "").strip()
        if not name or not path_data or path_data in seen_path_data:
            continue
        seen_path_data.add(path_data)
        outlines[name] = _flatten_svg_path(path_data)

    adjacency = {name: set() for name in outlines}
    distances = []
    names = list(outlines)
    for index, first_name in enumerate(names):
        for second_name in names[index + 1 :]:
            distance = _path_distance(
                outlines[first_name], outlines[second_name], tolerance
            )
            if math.isfinite(distance):
                distances.append((distance, first_name, second_name))
            if distance <= tolerance:
                adjacency[first_name].add(second_name)
                adjacency[second_name].add(first_name)

    for edge in REQUIRED_ADJACENCY_EDGES:
        first_name, second_name = tuple(edge)
        if first_name not in adjacency or second_name not in adjacency:
            raise ValueError(f"Required adjacency edge references an unknown territory: {sorted(edge)}")
        adjacency[first_name].add(second_name)
        adjacency[second_name].add(first_name)

    for edge in FORBIDDEN_ADJACENCY_EDGES:
        first_name, second_name = tuple(edge)
        if first_name in adjacency and second_name in adjacency:
            adjacency[first_name].discard(second_name)
            adjacency[second_name].discard(first_name)
    return adjacency, sorted(distances)


def ensure_svg_territories(db: Session, svg_path: Path):
    root = ET.parse(svg_path).getroot()
    existing = {
        territory.name: territory for territory in db.query(Territory).all()
    }
    created = []
    seen_path_data = set()
    for element in root.iter():
        if not element.tag.endswith("path"):
            continue
        if "interactive-region" not in element.attrib.get("class", ""):
            continue
        name = (element.attrib.get("data-name") or "").strip()
        path_data = (element.attrib.get("d") or "").strip()
        if not name or not path_data or path_data in seen_path_data:
            continue
        seen_path_data.add(path_data)
        territory = existing.get(name)
        if territory:
            territory.svg_path_data = path_data
            continue
        military_level = initial_military_level(name)
        territory = Territory(
            name=name,
            region=(element.attrib.get("data-region") or "unknown").strip(),
            description=(
                element.attrib.get("data-description")
                or f"{name}: территория Средиземья."
            ).strip(),
            svg_path_data=path_data,
            resource_wealth=80,
            strategic_value=round(military_level * 2 / 3, 1),
            population=300,
            fortifications=military_level,
            trade_routes=[],
            special_resources=[],
            climate="temperate",
            terrain="plains",
            status="neutral",
            development_level=0,
            offense_level=military_level,
            adjacent_territory_ids=[],
            resource_type="wood",
            resource_output=1,
        )
        db.add(territory)
        existing[name] = territory
        created.append(name)
    db.commit()
    return created


def _adjacency_fingerprint(adjacency):
    payload = {
        name: sorted(neighbor_names)
        for name, neighbor_names in sorted(adjacency.items())
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _database_adjacency(territories):
    by_id = {territory.id: territory.name for territory in territories}
    return {
        territory.name: {
            by_id[neighbor_id]
            for neighbor_id in (territory.adjacent_territory_ids or [])
            if neighbor_id in by_id
        }
        for territory in territories
    }


def audit_territory_adjacency(adjacency):
    unknown_neighbors = []
    asymmetric_edges = []
    for name, neighbor_names in adjacency.items():
        for neighbor_name in neighbor_names:
            if neighbor_name not in adjacency:
                unknown_neighbors.append((name, neighbor_name))
            elif name not in adjacency[neighbor_name]:
                asymmetric_edges.append((name, neighbor_name))

    missing_required_edges = [
        tuple(sorted(edge))
        for edge in REQUIRED_ADJACENCY_EDGES
        if not all(
            second in adjacency.get(first, set())
            for first, second in (tuple(edge), tuple(reversed(tuple(edge))))
        )
    ]
    present_forbidden_edges = [
        tuple(sorted(edge))
        for edge in FORBIDDEN_ADJACENCY_EDGES
        if all(
            second in adjacency.get(first, set())
            for first, second in (tuple(edge), tuple(reversed(tuple(edge))))
        )
    ]
    isolated = sorted(name for name, neighbors in adjacency.items() if not neighbors)
    unvisited = set(adjacency)
    components = []
    while unvisited:
        start = min(unvisited)
        stack = [start]
        component = set()
        while stack:
            name = stack.pop()
            if name in component:
                continue
            component.add(name)
            stack.extend(adjacency.get(name, set()) - component)
        unvisited -= component
        components.append(sorted(component))
    components.sort(key=lambda items: (-len(items), items))
    return {
        "territory_count": len(adjacency),
        "edge_count": sum(len(neighbors) for neighbors in adjacency.values()) // 2,
        "unknown_neighbors": sorted(unknown_neighbors),
        "asymmetric_edges": sorted(asymmetric_edges),
        "missing_required_edges": sorted(missing_required_edges),
        "present_forbidden_edges": sorted(present_forbidden_edges),
        "isolated_territories": isolated,
        "connected_components": components,
    }


def sync_territory_adjacency(
    db: Session, svg_path: Path, tolerance=DEFAULT_BORDER_TOLERANCE
):
    adjacency, distances = infer_svg_adjacency(svg_path, tolerance)
    territories = db.query(Territory).all()
    by_name = {territory.name: territory for territory in territories}
    missing_in_database = sorted(set(adjacency) - set(by_name))
    missing_in_svg = sorted(set(by_name) - set(adjacency))
    if missing_in_database or missing_in_svg:
        raise ValueError(
            "Territory map mismatch: "
            f"missing in database={missing_in_database}, missing in SVG={missing_in_svg}"
        )

    audit = audit_territory_adjacency(adjacency)
    failures = {
        key: audit[key]
        for key in (
            "unknown_neighbors",
            "asymmetric_edges",
            "missing_required_edges",
            "present_forbidden_edges",
        )
        if audit[key]
    }
    if failures:
        raise ValueError(f"Territory adjacency audit failed: {failures}")

    for name, neighbor_names in adjacency.items():
        territory = by_name[name]
        territory.adjacent_territory_ids = sorted(by_name[item].id for item in neighbor_names)
    db.commit()
    return adjacency, distances


def ensure_territory_adjacency(db: Session, svg_path: Path):
    territories = db.query(Territory).all()
    current = _database_adjacency(territories)
    if _adjacency_fingerprint(current) == EXPECTED_ADJACENCY_FINGERPRINT:
        return False

    adjacency, _ = sync_territory_adjacency(db, svg_path)
    fingerprint = _adjacency_fingerprint(adjacency)
    if fingerprint != EXPECTED_ADJACENCY_FINGERPRINT:
        raise ValueError(
            "SVG adjacency changed; review the generated routes and update the "
            f"fingerprint (actual: {fingerprint})"
        )
    return True
