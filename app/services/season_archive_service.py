import base64
import binascii
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session, defer

from app.core.time import as_utc
from app.models.campaign import CampaignSeason, CampaignSeasonClanResult
from app.models.clan import Clan
from app.models.season_archive import CampaignSeasonArchive
from app.models.territory import Territory


MAP_ASSET_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public"
SVG_NS = "http://www.w3.org/2000/svg"
SCHEMA_VERSION = 1

# Keep the order, aliases and image deduplication of content/clanAwards.js.
REGION_AWARDS = (
    ("angmar", "region-angmar", "clan_award_angmar"),
    ("arnor", "region-arnor", "clan_award_arnor"),
    ("eriador", "region-arnor", "clan_award_eriador"),
    ("dwarf", "region-dwarves", "clan_award_dwarf"),
    ("misty", "region-dwarves", "clan_award_misty"),
    ("goblin", "region-goblins", "clan_award_goblin"),
    ("gondor", "region-gondor", "clan_award_gondor"),
    ("harad", "region-harad", "clan_award_harad"),
    ("imladris", "region-imladris", "clan_award_imladris"),
    ("isengard", "region-isengard", "clan_award_isengard"),
    ("isen", "region-isengard", "clan_award_isengard"),
    ("lothlorien", "region-lothlorien", "clan_award_lothlorien"),
    ("mordor", "region-mordor", "clan_award_mordor"),
    ("rhun", "region-rhun", "clan_award_rhun"),
    ("rohan", "region-rohan", "clan_award_rohan"),
)
SEASON_AWARDS = {
    1: ("season-champion", "clan_award_season_champion"),
    2: ("season-runner-up", "clan_award_season_second"),
    3: ("season-third", "clan_award_season_third"),
}
TERRITORY_FIELDS = (
    "id", "name", "region", "svg_path_data", "owner_clan_id", "is_playable",
    "is_coastal", "has_port", "stronghold_power", "development_level",
    "fortifications", "offense_level", "port_level", "fleet_level",
    "influence_value", "required_influence", "required_territories", "population",
    "resource_wealth", "strategic_value", "resource_type", "resource_output",
    "secondary_resource_type",
)
RESULT_FIELDS = (
    "clan_id", "clan_name", "clan_avatar_url", "clan_map_color", "rank",
    "influence", "base_influence", "territory_count", "wars_won", "wars_lost",
    "defenses_won", "gold", "iron", "wood", "food", "mithril",
)


def _timestamp(value):
    return as_utc(value).isoformat() if value is not None else None


def _award(key, label_key, description_key):
    return {"key": key, "image": f"/assets/awards/clan/{key}.png",
            "label_key": label_key, "description_key": description_key}


class SeasonArchiveService:
    """Insert once during completion; public reads never consult live map data."""

    def capture(self, db: Session, season: CampaignSeason) -> CampaignSeasonArchive:
        existing = db.get(CampaignSeasonArchive, season.id)
        if existing is not None:
            return existing
        if season.status != "completed" or season.ends_at is None:
            raise ValueError("Only a completed season can be archived")

        view_box, map_svg = self._freeze_map()
        owners = {clan.id: clan for clan in db.query(Clan).filter(Clan.is_deleted.is_(False)).all()}
        territories = []
        for territory in db.query(Territory).order_by(Territory.id).all():
            owner = owners.get(territory.owner_clan_id)
            territories.append({
                **{field: getattr(territory, field) for field in TERRITORY_FIELDS},
                "owner_clan_id": owner.id if owner else None,
                "owner_clan_name": owner.name if owner else None,
                "owner_clan_map_color": owner.map_color if owner and not owner.is_admin_clan else None,
            })
        clans = []
        results = db.query(CampaignSeasonClanResult).filter_by(season_id=season.id).order_by(
            CampaignSeasonClanResult.rank, CampaignSeasonClanResult.id,
        ).all()
        for result in results:
            regional = {}
            for territory in territories:
                if territory["owner_clan_id"] != result.clan_id:
                    continue
                source = f'{territory["region"] or ""} {territory["name"] or ""}'.lower()
                match = next((award for award in REGION_AWARDS if award[0] in source), None)
                if match:
                    _, key, label_key = match
                    regional[key] = _award(key, label_key, "clan_award_regional_description")
            placement = SEASON_AWARDS.get(result.rank)
            awards = [_award(*placement, "clan_award_season_description")] if placement else []
            clans.append({
                **{field: getattr(result, field) for field in RESULT_FIELDS},
                "captured_at": _timestamp(result.captured_at),
                "awards": awards + list(regional.values()),
            })
        payload = {
            "season": {"id": season.id, "number": season.number, "name": season.name,
                       "starts_at": _timestamp(season.starts_at), "ends_at": _timestamp(season.ends_at)},
            "view_box": view_box, "territories": territories, "clans": clans,
            "captured_at": _timestamp(season.ends_at), "schema_version": SCHEMA_VERSION,
        }
        canonical = json.dumps({"payload": payload, "map_svg": map_svg}, ensure_ascii=False,
                               sort_keys=True, separators=(",", ":")).encode("utf-8")
        archive = CampaignSeasonArchive(
            season_id=season.id, captured_at=season.ends_at, schema_version=SCHEMA_VERSION,
            payload=payload, map_svg=map_svg, checksum=hashlib.sha256(canonical).hexdigest(),
        )
        db.add(archive)
        db.flush()
        return archive

    @staticmethod
    def _read_svg(path):
        content = path.read_bytes()
        if b"<!doctype" in content.lower() or b"<!entity" in content.lower():
            raise ValueError("Archive SVG must not contain a DTD or entities")
        return ET.fromstring(content)

    @staticmethod
    def _numbers(value, count):
        parts = re.split(r"[\s,]+", value.strip())
        if len(parts) != count or not all(math.isfinite(float(part)) for part in parts):
            raise ValueError("Invalid archive map geometry")
        return parts

    def _freeze_map(self):
        try:
            interactive = self._read_svg(MAP_ASSET_DIR / "map-interactive.svg")
            view_box = interactive.attrib["viewBox"]
            parts = self._numbers(view_box, 4)
            if float(parts[2]) <= 0 or float(parts[3]) <= 0:
                raise ValueError("Invalid archive map dimensions")
            source = self._read_svg(MAP_ASSET_DIR / "map.svg")
            root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": view_box})
            # Only raster data and numeric placement survive; no source SVG/CSS code is served.
            for node in source.iter(f"{{{SVG_NS}}}image"):
                href = node.get("href") or node.get("{http://www.w3.org/1999/xlink}href", "")
                match = re.fullmatch(r"data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=\s]+)", href)
                if not match:
                    continue
                mime, encoded = match.groups()
                encoded = "".join(encoded.split())
                data = base64.b64decode(encoded, validate=True)
                if not ((mime == "jpeg" and data.startswith(b"\xff\xd8\xff")) or
                        (mime == "png" and data.startswith(b"\x89PNG\r\n\x1a\n")) or
                        (mime == "webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP")):
                    raise ValueError("Invalid embedded archive raster")
                attributes = {"href": f"data:image/{mime};base64,{encoded}"}
                for field in ("x", "y", "width", "height"):
                    if field in node.attrib:
                        self._numbers(node.attrib[field], 1)
                        attributes[field] = node.attrib[field]
                if "transform" in node.attrib:
                    matrix = re.fullmatch(r"matrix\(([^()]+)\)", node.attrib["transform"])
                    if not matrix:
                        raise ValueError("Invalid archive raster transform")
                    self._numbers(matrix[1], 6)
                    attributes["transform"] = node.attrib["transform"]
                ET.SubElement(root, "image", attributes)
            if not len(root):
                raise ValueError("Archive backdrop has no embedded raster")
            return view_box, ET.tostring(root, encoding="unicode")
        except (OSError, ET.ParseError, KeyError, binascii.Error) as error:
            raise ValueError("Unable to freeze archive map assets") from error

    @staticmethod
    def _public_query(db):
        return db.query(CampaignSeasonArchive).options(defer(CampaignSeasonArchive.map_svg)).join(
            CampaignSeason, CampaignSeason.id == CampaignSeasonArchive.season_id,
        ).filter(CampaignSeason.status == "completed")

    def get(self, db: Session, season_id: int) -> CampaignSeasonArchive | None:
        return self._public_query(db).filter(CampaignSeasonArchive.season_id == season_id).first()

    def list_seasons(self, db: Session) -> list[dict]:
        archives = self._public_query(db).order_by(
            CampaignSeasonArchive.captured_at.desc(), CampaignSeasonArchive.season_id.desc(),
        ).all()
        return [{
            **deepcopy(archive.payload["season"]), "status": "completed",
            "captured_at": archive.payload["captured_at"], "schema_version": archive.schema_version,
            "checksum": archive.checksum, "clan_count": len(archive.payload["clans"]),
            "winner": deepcopy(archive.payload["clans"][0]) if archive.payload["clans"] else None,
        } for archive in archives]

    def detail(self, db: Session, season_id: int) -> dict | None:
        archive = self.get(db, season_id)
        if archive is None:
            return None
        return {**deepcopy(archive.payload), "map_image_url": f"/api/v1/campaign/archives/{season_id}/map.svg"}
