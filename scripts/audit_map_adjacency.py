from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.territory_adjacency_service import (
    DEFAULT_BORDER_TOLERANCE,
    FORBIDDEN_ADJACENCY_EDGES,
    REQUIRED_ADJACENCY_EDGES,
    audit_territory_adjacency,
    infer_svg_adjacency,
)


MAP_PATH = (
    PROJECT_ROOT
    / "frontend"
    / "public"
    / "map-interactive.svg"
)
REVIEW_TOLERANCE = 45.0


def main() -> None:
    adjacency, distances = infer_svg_adjacency(MAP_PATH)
    audit = audit_territory_adjacency(adjacency)
    reviewed = REQUIRED_ADJACENCY_EDGES | FORBIDDEN_ADJACENCY_EDGES
    close_gaps = {
        frozenset((first, second))
        for distance, first, second in distances
        if DEFAULT_BORDER_TOLERANCE < distance <= REVIEW_TOLERANCE
    }
    unreviewed = close_gaps - reviewed

    print(
        f"Territories: {audit['territory_count']}; "
        f"land borders: {audit['edge_count']}; "
        f"component sizes: {[len(item) for item in audit['connected_components']]}"
    )
    print(f"Isolated land contours: {audit['isolated_territories']}")
    print(f"Required reviewed edges: {[sorted(item) for item in REQUIRED_ADJACENCY_EDGES]}")
    print(f"Forbidden reviewed edges: {[sorted(item) for item in FORBIDDEN_ADJACENCY_EDGES]}")
    if (
        audit["unknown_neighbors"]
        or audit["asymmetric_edges"]
        or audit["missing_required_edges"]
        or audit["present_forbidden_edges"]
        or unreviewed
    ):
        raise SystemExit(
            "Adjacency audit failed: "
            f"unknown={audit['unknown_neighbors']}, "
            f"asymmetric={audit['asymmetric_edges']}, "
            f"missing_required={audit['missing_required_edges']}, "
            f"present_forbidden={audit['present_forbidden_edges']}, "
            f"unreviewed_close_gaps={[sorted(item) for item in unreviewed]}"
        )
    print("Adjacency audit passed.")


if __name__ == "__main__":
    main()
