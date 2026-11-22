#!/usr/bin/env python3
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from sqlalchemy import or_

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.core.security import get_password_hash
from app.database import SessionLocal
from app.models.clan import Clan, ClanMember
from app.models.match import Match
from app.models.role import Role
from app.models.territory import Territory
from app.models.user import User


API_URL = "https://bfmeladder.com/api/replays"
PATCH_ID = "05a64473-c7f5-4fff-8e00-f30e06db9d96:1.9.7.7d"
PATCH_NAME = "Ennorath (1.9.7.7d)"
DEFAULT_PASSWORD = "ladder123"

FACTIONS_EN_TO_RU = {
    "gondor": "Гондор",
    "rohan": "Рохан",
    "isengard": "Изенгард",
    "mordor": "Мордор",
    "angmar": "Ангмар",
    "dwarves": "Гномы",
    "elves": "Эльфы",
    "goblins": "Гоблины",
    "men": "Люди",
    "harad": "Харад",
    "arnor": "Арнор",
    "lothlorien": "Лотлориэн",
    "imladris": "Имладрис",
    "misty mountains": "Мглистые Горы",
}

REGION_LABELS = {
    "eriador": "Эриадор",
    "lindon": "Линдон",
    "misty-mountains": "Мглистые горы",
    "rhovanion": "Рованион",
    "angmar": "Ангмар",
    "rohan": "Рохан",
    "isen": "Изен",
    "gondor": "Гондор",
    "mordor": "Мордор",
    "harad": "Харад",
    "rhun": "Рун",
}


def normalize_faction(name):
    if not name:
        return "Неизвестно"
    return FACTIONS_EN_TO_RU.get(str(name).strip().lower(), str(name).strip())


def parse_match_date(value):
    value = str(value or "")
    if value.isdigit():
        timestamp = int(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return datetime.fromtimestamp(timestamp)
    return datetime.utcnow()


def normalize_username(value):
    value = str(value or "").strip()
    # Display names are public source data. Keep punctuation such as '-' and '.'
    # so the local profile matches the nickname shown by the ladder.
    return value[:32] if value else None


def player_display_name(player):
    for key in ("PlayerName", "PlayerAccountName", "Username", "Name", "Nickname"):
        if player.get(key):
            return str(player[key]).strip()
    # UUID is an internal identifier, never a display nickname.
    return None


def seed_svg_territories(db):
    svg_path = ROOT / "frontend" / "public" / "map-interactive.svg"
    root = ET.fromstring(svg_path.read_text(encoding="utf-8"))
    created = 0
    updated = 0
    skipped_duplicate_paths = 0
    seen_paths = set()

    for element in root.iter():
        if not element.tag.endswith("path"):
            continue
        class_name = element.attrib.get("class", "")
        if "interactive-region" not in class_name:
            continue

        name = (element.attrib.get("data-name") or "").strip()
        region = (element.attrib.get("data-region") or "").strip()
        path_data = (element.attrib.get("d") or "").strip()
        if not name or not path_data:
            continue
        if path_data in seen_paths:
            skipped_duplicate_paths += 1
            continue
        seen_paths.add(path_data)

        territory = db.query(Territory).filter(Territory.svg_path_data == path_data).first()

        defaults = {
            "name": name,
            "region": region or "unknown",
            "description": f"{name}: отдельная локация региона {REGION_LABELS.get(region, region or 'Средиземье')}.",
            "svg_path_data": path_data,
            "resource_wealth": max(1, min(10, len(name) % 10 + 1)),
            "strategic_value": max(1, min(10, len(region) % 10 + 1)),
            "population": (len(name) % 9 + 1) * 100,
            "fortifications": len(path_data) % 6,
            "trade_routes": [],
            "special_resources": [],
            "climate": "temperate",
            "terrain": "mixed",
            "status": "neutral",
        }

        if territory:
            for key, value in defaults.items():
                if key == "status" and territory.status:
                    continue
                setattr(territory, key, value)
            updated += 1
        else:
            db.add(Territory(**defaults))
            created += 1

    db.flush()

    removed_duplicate_rows = 0
    seen_db_paths = set()
    for territory in db.query(Territory).order_by(Territory.id).all():
        path_data = (territory.svg_path_data or "").strip()
        if not path_data:
            continue
        if path_data in seen_db_paths:
            db.delete(territory)
            removed_duplicate_rows += 1
            continue
        seen_db_paths.add(path_data)

    db.commit()
    return {
        "created": created,
        "updated": updated,
        "skipped_duplicate_paths": skipped_duplicate_paths,
        "removed_duplicate_rows": removed_duplicate_rows,
        "total": db.query(Territory).count(),
    }


def fetch_replays():
    try:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(API_URL, timeout=90, verify=False)
        response.raise_for_status()
        return response.json(), "bfmeladder.com/api/replays"
    except Exception as exc:
        cache_path = ROOT / "scripts" / "bfmeladder-com-api-replays.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8")), f"cache fallback: {cache_path.name} ({exc})"
        raise


def is_ennorath(match):
    return (
        PATCH_ID in str(match.get("PatchId", ""))
        or PATCH_NAME in str(match.get("PatchName", ""))
    ) and "RotWK" in str(match.get("GameName", ""))


def is_relevant_rotwk(match):
    return (
        "RotWK" in str(match.get("GameName", ""))
        and str(match.get("GamemodeName", "")).lower() == "1 versus 1"
        and len(match.get("Players") or []) >= 2
    )


def extract_match(match_id, match):
    players = match.get("Players") or []
    winners = [player for player in players if player.get("IsWinner") is True]
    losers = [player for player in players if player.get("IsWinner") is False]
    if not winners or not losers:
        return None

    winner = winners[0]
    loser = losers[0]
    winner_name = player_display_name(winner)
    loser_name = player_display_name(loser)
    if not winner_name or not loser_name:
        return None

    return {
        "match_id": match_id,
        "winner_player": normalize_username(winner_name),
        "winner_source_name": winner_name,
        "winner_faction": normalize_faction(winner.get("FactionName")),
        "loser_player": normalize_username(loser_name),
        "loser_source_name": loser_name,
        "loser_faction": normalize_faction(loser.get("FactionName")),
        "match_date": parse_match_date(match.get("Date")),
        "duration": match.get("Duration"),
        "map_name": match.get("MapName"),
        "game_mode": match.get("GamemodeName"),
        "patch_version": match.get("PatchName"),
        "arena_id": match.get("ArenaId"),
        "patch_id": match.get("PatchId"),
        "patch_name": match.get("PatchName"),
        "game_name": match.get("GameName"),
        "map_id": match.get("MapId"),
        "map_preview_source": match.get("MapPreviewSource"),
        "gamemode_name": match.get("GamemodeName"),
        "elo_delta": match.get("EloDelta"),
        "downloads": match.get("Downloads"),
        "likes": json.dumps(match.get("Likes") or [], ensure_ascii=False),
        "comments": json.dumps(match.get("Comments") or [], ensure_ascii=False),
        "is_valid": match.get("IsValid"),
        "is_qualification_round": match.get("IsQualificationRound"),
        "winner_player_uuid": winner.get("PlayerAccountUuid"),
        "loser_player_uuid": loser.get("PlayerAccountUuid"),
        "winner_faction_index": winner.get("FactionIndex"),
        "loser_faction_index": loser.get("FactionIndex"),
        "winner_old_rank": winner.get("OldRank"),
        "winner_new_rank": winner.get("NewRank"),
        "loser_old_rank": loser.get("OldRank"),
        "loser_new_rank": loser.get("NewRank"),
    }


def save_matches(db, extracted):
    created = 0
    for item in extracted:
        existing = db.query(Match).filter(Match.match_id == item["match_id"]).first()
        fields = {key: value for key, value in item.items() if key not in {"winner_source_name", "loser_source_name"}}
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
        else:
            db.add(Match(**fields, is_live=False))
            created += 1
    db.commit()
    return created


def ensure_role(db, name):
    role = db.query(Role).filter(Role.name == name).first()
    if role:
        return role
    role = Role(name=name, description=name)
    db.add(role)
    db.flush()
    return role


def ensure_users_and_clans(db, extracted, limit):
    user_role = ensure_role(db, "user")
    player_names = []
    seen = set()
    for match in extracted:
        for username in (match["winner_player"], match["loser_player"]):
            if username and username not in seen:
                seen.add(username)
                player_names.append(username)
            if len(player_names) >= limit:
                break
        if len(player_names) >= limit:
            break

    created_users = []
    for username in player_names:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            user = User(
                username=username,
                email=f"{username}@ladder.local",
                hashed_password=get_password_hash(DEFAULT_PASSWORD),
                is_active=True,
                role_id=user_role.id,
                balance=500,
                level=3,
                experience=250,
                language="ru",
                allow_clan_invites=True,
            )
            db.add(user)
            db.flush()
        created_users.append(user)

    clans = []
    for idx, user in enumerate(created_users[:3], start=1):
        clan_name = f"Ladder {idx}: {user.username}"
        clan = db.query(Clan).filter(Clan.name == clan_name).first()
        if not clan:
            clan = Clan(
                name=clan_name,
                description=f"Клан для проверки статистики игрока {user.username}",
                leader_id=user.id,
                level=idx,
                experience=idx * 100,
                max_members=20,
            )
            db.add(clan)
            db.flush()
        if not db.query(ClanMember).filter(ClanMember.user_id == user.id).first():
            db.add(ClanMember(user_id=user.id, clan_id=clan.id, rank="Лидер"))
        clans.append(clan)

    territories = db.query(Territory).order_by(Territory.id).limit(len(clans)).all()
    for territory, clan in zip(territories, clans):
        territory.owner_clan_id = clan.id
        territory.status = "active"
        if clan not in territory.defending_clans:
            territory.defending_clans.append(clan)
    if len(territories) > 1 and clans:
        target = territories[-1]
        attacker = clans[0]
        target.status = "contested"
        if attacker not in target.attacking_clans:
            target.attacking_clans.append(attacker)

    db.commit()
    return [{"username": user.username, "password": DEFAULT_PASSWORD} for user in created_users]


def build_stats(db, source, extracted, created_matches, users):
    faction_counter = Counter()
    map_counter = Counter()
    player_stats = defaultdict(lambda: {"wins": 0, "losses": 0})

    for item in extracted:
        faction_counter[item["winner_faction"]] += 1
        faction_counter[item["loser_faction"]] += 1
        if item["map_name"]:
            map_counter[item["map_name"]] += 1
        player_stats[item["winner_player"]]["wins"] += 1
        player_stats[item["loser_player"]]["losses"] += 1

    top_players = sorted(
        (
            {
                "username": username,
                "wins": data["wins"],
                "losses": data["losses"],
                "total": data["wins"] + data["losses"],
                "win_rate": round(data["wins"] / max(1, data["wins"] + data["losses"]) * 100, 1),
            }
            for username, data in player_stats.items()
        ),
        key=lambda item: (item["wins"], item["total"]),
        reverse=True,
    )[:10]

    return {
        "source": source,
        "parsed_matches": len(extracted),
        "created_or_new_matches": created_matches,
        "database_total_matches": db.query(Match).count(),
        "created_users": users,
        "top_factions": [{"faction": name, "count": count} for name, count in faction_counter.most_common(10)],
        "top_maps": [{"map": name, "count": count} for name, count in map_counter.most_common(10)],
        "top_players": top_players,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--users", type=int, default=3)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        territory_stats = seed_svg_territories(db)
        raw, source = fetch_replays()
        extracted = []
        iterator = raw.items() if isinstance(raw, dict) else enumerate(raw)
        for match_id, match in iterator:
            if not isinstance(match, dict) or not is_ennorath(match):
                continue
            item = extract_match(str(match_id), match)
            if item and item["winner_player"] and item["loser_player"]:
                extracted.append(item)
            if len(extracted) >= args.limit:
                break

        filter_mode = "RotWK Ennorath 1.9.7.7d"
        if not extracted:
            filter_mode = "fallback: current RotWK 1 versus 1"
            iterator = raw.items() if isinstance(raw, dict) else enumerate(raw)
            for match_id, match in iterator:
                if not isinstance(match, dict) or not is_relevant_rotwk(match):
                    continue
                item = extract_match(str(match_id), match)
                if item and item["winner_player"] and item["loser_player"]:
                    extracted.append(item)
                if len(extracted) >= args.limit:
                    break

        created_matches = save_matches(db, extracted)
        users = ensure_users_and_clans(db, extracted, args.users)
        stats = build_stats(db, source, extracted, created_matches, users)
        stats["filter_mode"] = filter_mode
        stats["territories"] = territory_stats

        report_path = ROOT / "parsed_ladder_stats.json"
        report_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        print(f"\nREPORT={report_path}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
