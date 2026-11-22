from pathlib import Path

from app.services.territory_adjacency_service import (
    DEFAULT_BORDER_TOLERANCE,
    EXPECTED_ADJACENCY_FINGERPRINT,
    FORBIDDEN_ADJACENCY_EDGES,
    REQUIRED_ADJACENCY_EDGES,
    _adjacency_fingerprint,
    audit_territory_adjacency,
    infer_svg_adjacency,
)
from app.services.bootstrap_service import (
    COASTAL_TERRITORIES,
    PORT_TERRITORIES,
    STRONGHOLD_RULES,
)


MAP_PATH = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "public"
    / "map-interactive.svg"
)


def test_full_map_adjacency_is_symmetric_and_reviewed():
    adjacency, distances = infer_svg_adjacency(MAP_PATH)
    audit = audit_territory_adjacency(adjacency)

    assert _adjacency_fingerprint(adjacency) == EXPECTED_ADJACENCY_FINGERPRINT
    assert audit["territory_count"] == 76
    assert audit["edge_count"] == 173
    assert audit["unknown_neighbors"] == []
    assert audit["asymmetric_edges"] == []
    assert audit["missing_required_edges"] == []
    assert audit["present_forbidden_edges"] == []
    assert audit["isolated_territories"] == ["Тол-Фалас"]
    assert [len(component) for component in audit["connected_components"]] == [75, 1]

    reviewed_edges = REQUIRED_ADJACENCY_EDGES | FORBIDDEN_ADJACENCY_EDGES
    close_gaps = {
        frozenset((first, second))
        for distance, first, second in distances
        if DEFAULT_BORDER_TOLERANCE < distance <= 45
    }
    assert close_gaps == reviewed_edges


def test_known_itilien_morgul_gap_is_connected():
    adjacency, _ = infer_svg_adjacency(MAP_PATH)

    assert "Минас Моргул" in adjacency["Центральный Итилиен"]
    assert "Центральный Итилиен" in adjacency["Минас Моргул"]
    assert "Минас Моргул" not in adjacency["Удун"]


def test_reviewed_coastal_territories_include_new_sea_targets():
    assert {"Арнор", "Река Адорн", "Умбар"} <= COASTAL_TERRITORIES
    assert "Умбар" in PORT_TERRITORIES
    assert "Энедвайт" in PORT_TERRITORIES
    assert "Лебеннин" in COASTAL_TERRITORIES
    assert "Лебеннин" not in PORT_TERRITORIES


def test_helms_deep_is_a_great_stronghold():
    required_territories, stronghold_power = STRONGHOLD_RULES[
        "Хельмова Падь (Западная Марка)"
    ]
    assert required_territories == 5
    assert stronghold_power == 4
