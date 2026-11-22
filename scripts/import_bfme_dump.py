#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_bfme_dump.py
---------------------------------
Utility script for ClanWar project to:
  1) Normalize/clean existing matches in DB (unify factions -> Russian, drop LIVE, dedupe by match_id).
  2) Import completed matches from a saved "BFME Arena" HTML dump (DevTools 'Save as...').

Usage:
  # Dry-run normalize (show planned changes only)
  python import_bfme_dump.py normalize --dry-run

  # Apply normalization
  python import_bfme_dump.py normalize

  # Import from a saved HTML dump
  python import_bfme_dump.py import --html /path/to/BFME\ Arena.html

  # Import with date filter (only matches on this date)
  python import_bfme_dump.py import --html BFME\ Arena.html --date 2025-08-22

Notes:
- The script assumes it runs from the project root and can import your modules:
  database.py, models.py, schemas.py
- Only completed matches are imported (cards labeled "Winners"/"Losers").
- LIVE cards ("Team 1"/"Team 2" or with LIVE link) are skipped.
"""

import argparse
import sys
import os
from datetime import datetime, date
from typing import Optional, Tuple, List, Dict

from bs4 import BeautifulSoup  # pip install beautifulsoup4

# Wire up project modules
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from database import get_db  # type: ignore
from models import Match  # type: ignore
from schemas import MatchCreate  # type: ignore
from crud import create_match  # type: ignore

# ---------- Faction normalization ----------

# Map any possible icon filename OR English label to the single Russian canonical name.
FACTION_CANON = {
    # Russian already (canonical)
    "Гондор": "Гондор",
    "Рохан": "Рохан",
    "Изенгард": "Изенгард",
    "Мордор": "Мордор",
    "Ангмар": "Ангмар",
    "Гномы": "Гномы",
    "Эльфы": "Эльфы",
    "Гоблины": "Гоблины",
    "Дейл": "Дейл",
    "Рун": "Рун",
    "Харад": "Харад",
    "Арнор": "Арнор",
    "Лотлориэн": "Лотлориэн",
    "Имладрис": "Имладрис",
    "Мглистые Горы": "Мглистые Горы",

    # English -> Russian
    "Men": "Гондор", "Gondor": "Гондор",
    "Rohan": "Рохан",
    "Isengard": "Изенгард",
    "Mordor": "Мордор",
    "Angmar": "Ангмар",
    "Dwarves": "Гномы", "Dwarf": "Гномы",
    "Elves": "Эльфы", "Elf": "Эльфы",
    "Goblins": "Гоблины", "Goblin": "Гоблины",
    "Dale": "Дейл",
    "Rhun": "Рун", "Rhûn": "Рун",
    "Harad": "Харад",
    "Arnor": "Арнор",
    "Lothlorien": "Лотлориэн", "Lórien": "Лотлориэн",
    "Imladris": "Имладрис", "Rivendell": "Имладрис",
    "Misty Mountains": "Мглистые Горы", "Misty_Mountains": "Мглистые Горы",
}

# Icon filename (last path segment) -> English, then will be mapped to Russian via FACTION_CANON above.
ICON_TO_EN = {
    # simple names observed on arena
    "mordor.png": "Mordor",
    "men.png": "Men",
    "rohan.png": "Rohan",
    "isengard.png": "Isengard",
    "angmar.png": "Angmar",
    "dwarves.png": "Dwarves",
    "elves.png": "Elves",
    "goblins.png": "Goblins",
    "harad.png": "Harad",
    "arnor.png": "Arnor",
    "lothlorien.png": "Lothlorien",
    "imladris.png": "Imladris",
    "misty_mountains.png": "Misty Mountains",
    # GUID-like filenames seen in your codebase mapping
    "014c1ebf-1d53-4b29-9914-1fa3e44dae0c.png": "Harad",
    "806c09f6-3abf-479b-b97a-b856d80b0e02.png": "Isengard",
    "73a97e8e-bd4c-450c-87d9-4596e7b68e59.png": "Misty Mountains",
    "e464285a-5cc1-457a-b1f6-012c5b10aa25.png": "Gondor",
    "0afa17d0-7d6f-4b42-a9f0-ad7dd2ac44bf.png": "Mordor",
    "fe8eff0d-d1d6-459c-8c0f-2ca1a38ee35f.png": "Lothlorien",
    "a983b2bd-64eb-412d-9872-5e35279b3ab0.png": "Imladris",
    "08217ec7-0c2d-4c68-9afa-e0c98f2d9c8d.png": "Arnor",
    "efcd9306-00a2-4dfd-8773-7ed8bce73e1b.png": "Rohan",
    "69eedfea-67c6-4ada-981b-8764a1045d44.png": "Angmar",
}

def canonical_faction_from_icon(icon_url: str) -> Optional[str]:
    if not icon_url:
        return None
    filename = icon_url.split('/')[-1]
    en = ICON_TO_EN.get(filename)
    if not en:
        # try to guess by filename stem
        stem = filename.split('.')[0].lower()
        guess_map = {
            "men":"Men","gondor":"Gondor","rohan":"Rohan","isengard":"Isengard","mordor":"Mordor",
            "angmar":"Angmar","dwarves":"Dwarves","elves":"Elves","goblins":"Goblins","harad":"Harad",
            "arnor":"Arnor","lothlorien":"Lothlorien","imladris":"Imladris",
            "misty_mountains":"Misty Mountains","mistymountains":"Misty Mountains",
            "mm":"Misty Mountains"
        }
        en = guess_map.get(stem)
    if not en:
        return None
    return FACTION_CANON.get(en, en)

def canonical_faction(name_or_icon: str) -> Optional[str]:
    if not name_or_icon:
        return None
    # if looks like a URL/path, treat as icon
    if "/" in name_or_icon or name_or_icon.endswith(".png"):
        return canonical_faction_from_icon(name_or_icon)
    return FACTION_CANON.get(name_or_icon, name_or_icon)

# ---------- Date helpers ----------

def parse_match_date(text: str) -> Optional[datetime]:
    """Accepts 'YYYY/MM/DD HH:MM', 'YYYY/MM/DD', 'DD.MM.YYYY', or epoch ms/seconds as str."""
    if not text:
        return None
    t = text.strip()
    try:
        if t.isdigit():
            # epoch - could be ms or s
            iv = int(t)
            if iv > 10_000_000_000:  # looks like ms
                iv = iv // 1000
            return datetime.fromtimestamp(iv)
        if " " in t and "/" in t:
            return datetime.strptime(t, "%Y/%m/%d %H:%M")
        if "/" in t:
            return datetime.strptime(t, "%Y/%m/%d")
        if "." in t:
            return datetime.strptime(t, "%d.%m.%Y")
    except Exception:
        return None
    return None

# ---------- HTML parsing ----------

def find_completed_sections(replay_div) -> Tuple[Optional[object], Optional[object]]:
    """Return winners_section, losers_section for completed games; otherwise (LIVE) -> (None, None)."""
    big_texts = replay_div.find_all("div", {"class": "bigText"})
    winners_section = None
    losers_section = None
    label_left = None
    label_right = None
    for bt in big_texts:
        txt = (bt.get_text() or "").strip().lower()
        if "winners" in txt:
            winners_section = bt.find_parent()
        if "losers" in txt:
            losers_section = bt.find_parent()
        if "team 1" in txt:
            label_left = bt.find_parent()
        if "team 2" in txt:
            label_right = bt.find_parent()
    # If it's labeled Teams and has LIVE link, we treat it as live/incomplete
    live_link = replay_div.find("a", string=lambda s: s and "LIVE" in s)
    if (label_left or label_right) or live_link:
        return None, None
    return winners_section, losers_section

def extract_players_from_section(section) -> List[Tuple[str,str]]:
    """Return list of (player_name, faction_ru)."""
    players = []
    # containers with style 'align-items: center'
    divs = section.find_all("div", style=lambda v: v and "align-items: center" in v)
    for container in divs:
        # The name/faction wrapper: a <div> with font-weight:800; inside may be <img class="armyIcon">
        name_div = container.find("div", style=lambda v: v and "font-weight: 800" in v)
        if not name_div:
            continue
        # Player name is text; armyIcon img may be before or after
        img = name_div.find("img", {"class": "armyIcon"})
        player_name = name_div.get_text(strip=True)
        faction_ru = None
        if img and img.get("src"):
            faction_ru = canonical_faction_from_icon(img.get("src"))
        # fallback: try to detect in text (rare on this page)
        if not faction_ru:
            # no reliable text on arena; skip if unknown
            continue
        players.append((player_name, faction_ru))
    return players

def extract_duration(replay_div) -> Optional[str]:
    for row in replay_div.find_all("div"):
        txt = row.get_text(strip=True)
        if txt == "Duration":
            val = row.find_parent()
            if val:
                sib = val.find_next_sibling()
                if sib:
                    return sib.get_text(strip=True)
    return None

def extract_map_name(replay_div) -> Optional[str]:
    block = replay_div.find("div", {"class": "mapImageBlock"})
    if not block:
        return None
    name_div = block.find("div", style=lambda v: v and "font-weight: 800" in v and "text-align: center" in v)
    return name_div.get_text(strip=True) if name_div else None

def extract_date_text(replay_div) -> Optional[str]:
    elem = replay_div.find("div", {"class": "unixDate"})
    if not elem:
        return None
    return elem.get_text(strip=True)

# ---------- Actions ----------

def action_normalize(dry_run: bool = False) -> int:
    """Normalize existing Match rows:
       - unify winner_faction/loser_faction to Russian
       - drop rows marked is_live = True
       - dedupe by match_id (keep newest created_at)"""
    db = next(get_db())
    changed = 0

    # 1) Drop LIVE
    live_qs = db.query(Match).filter(Match.is_live == True).all()
    for m in live_qs:
        if dry_run:
            print(f"[DRY] DELETE LIVE id={m.id} match_id={m.match_id}")
        else:
            db.delete(m)
            changed += 1
    if not dry_run:
        db.commit()

    # 2) Dedupe by match_id (keep max created_at)
    from sqlalchemy import func
    dup_ids = []
    sub = (
        db.query(Match.match_id, func.max(Match.created_at).label("max_created"))
        .group_by(Match.match_id)
        .subquery()
    )
    dups = (
        db.query(Match)
        .join(sub, (Match.match_id == sub.c.match_id) & (Match.created_at != sub.c.max_created))
        .all()
    )
    for m in dups:
        if dry_run:
            print(f"[DRY] DELETE DUP id={m.id} match_id={m.match_id}")
        else:
            dup_ids.append(m.id)
            db.delete(m)
            changed += 1
    if not dry_run:
        db.commit()

    # 3) Normalize faction names to Russian
    all_matches = db.query(Match).all()
    for m in all_matches:
        new_w = canonical_faction(m.winner_faction)
        new_l = canonical_faction(m.loser_faction)
        if not new_w or not new_l:
            # if faction couldn't be determined, skip updating but keep row
            continue
        if new_w != m.winner_faction or new_l != m.loser_faction:
            if dry_run:
                print(f"[DRY] UPDATE id={m.id} {m.winner_faction}->{new_w} | {m.loser_faction}->{new_l}")
            else:
                m.winner_faction = new_w
                m.loser_faction = new_l
                changed += 1
    if not dry_run:
        db.commit()
    return changed

def action_import(html_path: str, date_filter_str: Optional[str] = None, commit: bool = True) -> int:
    if not os.path.exists(html_path):
        print(f"File not found: {html_path}")
        return 0
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")

    if date_filter_str:
        # normalize to YYYY/MM/DD for comparison
        try:
            if "-" in date_filter_str:
                df = datetime.strptime(date_filter_str, "%Y-%m-%d").strftime("%Y/%m/%d")
            elif "." in date_filter_str:
                df = datetime.strptime(date_filter_str, "%d.%m.%Y").strftime("%Y/%m/%d")
            elif "/" in date_filter_str:
                df = date_filter_str
            else:
                df = None
        except Exception:
            df = None
    else:
        df = None

    db = next(get_db())
    imported = 0

    for replay_div in soup.find_all("div", {"class": "replayItem"}):
        match_id = replay_div.get("id")
        if not match_id:
            continue

        winners_section, losers_section = find_completed_sections(replay_div)
        if not winners_section or not losers_section:
            # live or incomplete -> skip
            continue

        # date
        date_text = extract_date_text(replay_div)
        if not date_text:
            continue
        dt = parse_match_date(date_text)
        if not dt:
            continue

        # filter by date if provided
        if df:
            dt_norm = dt.strftime("%Y/%m/%d")
            if dt_norm != df:
                continue

        # players+factions
        winners = extract_players_from_section(winners_section)
        losers = extract_players_from_section(losers_section)
        if not winners or not losers:
            continue

        duration = extract_duration(replay_div)
        map_name = extract_map_name(replay_div)

        # Build match schema (only first player for 1v1 page, but safe anyway)
        w_name, w_fac = winners[0]
        l_name, l_fac = losers[0]

        match_create = MatchCreate(
            match_id=match_id,
            winner_player=w_name,
            winner_faction=canonical_faction(w_fac) or w_fac,
            loser_player=l_name,
            loser_faction=canonical_faction(l_fac) or l_fac,
            match_date=dt,
            duration=duration,
            game_mode="1 versus 1",
            map_name=map_name,
            patch_version=None,
            is_live=False,
        )

        # Upsert behaviour via crud.create_match
        if commit:
            create_match(db, match_create)
        imported += 1

    if commit:
        db.commit()
    return imported

def main():
    parser = argparse.ArgumentParser(description="ClanWar DB maintenance & BFME dump importer")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_norm = sub.add_parser("normalize", help="Normalize existing match rows")
    p_norm.add_argument("--dry-run", action="store_true", help="Show changes without writing DB")

    p_imp = sub.add_parser("import", help="Import completed matches from BFME Arena HTML dump")
    p_imp.add_argument("--html", required=True, help="Path to saved BFME Arena HTML file")
    p_imp.add_argument("--date", required=False, help="Only import matches for this date (YYYY-MM-DD | DD.MM.YYYY | YYYY/MM/DD)")
    p_imp.add_argument("--no-commit", action="store_true", help="Parse and validate without writing DB")

    args = parser.parse_args()

    if args.cmd == "normalize":
        changes = action_normalize(dry_run=args.dry_run)
        if args.dry_run:
            print(f"[DRY] Planned changes: {changes}")
        else:
            print(f"Applied changes: {changes}")
    elif args.cmd == "import":
        cnt = action_import(args.html, date_filter_str=args.date, commit=not args.no_commit)
        print(f"Imported matches: {cnt}")

if __name__ == "__main__":
    main()
