"""Audit and optionally clean campaign rows that have no living clan or war."""

import argparse
import sys
from pathlib import Path

from sqlalchemy import exists

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models.clan import Clan, ClanMember
from app.models.territory import (
    Territory,
    TerritoryAttackingClans,
    TerritoryDefendingClans,
)
from app.models.war import ClanWar
from app.services.clan_influence_service import ClanInfluenceService
from app.services.territory_ownership_service import TerritoryOwnershipService


def audit(db):
    empty_clan_ids = [
        clan_id
        for (clan_id,) in db.query(Clan.id)
        .filter(
            ~exists().where(ClanMember.clan_id == Clan.id),
            Clan.is_admin_clan.is_(False),
        )
        .all()
    ]
    empty_owned = (
        db.query(Territory)
        .filter(Territory.owner_clan_id.in_(empty_clan_ids))
        .all()
        if empty_clan_ids else []
    )
    stale_neutral = (
        db.query(Territory)
        .filter(
            Territory.owner_clan_id.is_(None),
            Territory.status != "neutral",
            ~exists().where(
                (ClanWar.territory_id == Territory.id)
                & (ClanWar.status == "active")
            ),
        )
        .all()
    )
    active_pairs = {
        (war.territory_id, war.attacking_clan_id, war.defending_clan_id)
        for war in db.query(ClanWar)
        .filter(ClanWar.status == "active")
        .all()
    }
    stale_attack = [
        row for row in db.query(TerritoryAttackingClans).all()
        if not any(
            territory_id == row.territory_id and attacker_id == row.clan_id
            for territory_id, attacker_id, _ in active_pairs
        )
    ]
    stale_defense = [
        row for row in db.query(TerritoryDefendingClans).all()
        if not any(
            territory_id == row.territory_id and defender_id == row.clan_id
            for territory_id, _, defender_id in active_pairs
        )
    ]
    return {
        "empty_clan_ids": empty_clan_ids,
        "empty_owned": empty_owned,
        "stale_neutral": stale_neutral,
        "stale_attack": stale_attack,
        "stale_defense": stale_defense,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        result = audit(db)
        print(f"empty_clans={len(result['empty_clan_ids'])}: {result['empty_clan_ids']}")
        print(
            "territories_of_empty_clans="
            f"{len(result['empty_owned'])}: {[row.name for row in result['empty_owned']]}"
        )
        print(f"stale_territory_statuses={len(result['stale_neutral'])}")
        print(f"stale_attack_links={len(result['stale_attack'])}")
        print(f"stale_defense_links={len(result['stale_defense'])}")
        if not args.apply:
            print("dry-run: no changes")
            return

        ownership = TerritoryOwnershipService()
        affected_clans = set()
        for territory in result["empty_owned"]:
            affected_clans.add(territory.owner_clan_id)
            ownership.transfer(
                db,
                territory,
                None,
                reason="orphan_clan_cleanup",
            )
            territory.status = "neutral"
        for territory in result["stale_neutral"]:
            territory.status = "neutral"
        for row in result["stale_attack"]:
            db.delete(row)
        for row in result["stale_defense"]:
            db.delete(row)
        db.flush()
        influence = ClanInfluenceService()
        for clan_id in affected_clans:
            if clan_id:
                influence.recalculate(
                    db,
                    clan_id,
                    operation_id=f"orphan-cleanup:{clan_id}",
                    action="orphan_territory_cleanup",
                    source_type="maintenance",
                )
        db.commit()
        print("cleanup applied")


if __name__ == "__main__":
    main()
