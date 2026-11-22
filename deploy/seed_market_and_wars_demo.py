import argparse

from app.database import SessionLocal
from app.core.time import utc_now
from app.models.clan import Clan
from app.models.market import MarketOffer
from app.models.territory import Territory
from app.models.war import ClanWar, ClanWarParticipant
from app.schemas.war import ClanWarCreate
from app.services.market_service import ClanMarketService
from app.services.territory_ownership_service import TerritoryOwnershipService
from app.services.war_service import ClanWarService


WAR_SCENARIOS = (
    {
        "attacker_id": 1,
        "defender_id": 3,
        "source_id": 2,
        "target_id": 85,
        "attacker_points": 70,
        "defender_points": 30,
    },
    {
        "attacker_id": 2,
        "defender_id": 14,
        "source_id": 3,
        "target_id": 67,
        "attacker_points": 35,
        "defender_points": 65,
    },
)

DEMO_CLAN_COLORS = {
    1: "#C97518",
    2: "#1E6FB9",
    3: "#B9323B",
    14: "#2E8B57",
}

LEGACY_RECIPROCAL_ROUTES = {
    (1, 2, 3),
    (2, 3, 2),
}


def close_legacy_reciprocal_wars(db) -> list[str]:
    messages = []
    now = utc_now()
    active_wars = db.query(ClanWar).filter(ClanWar.status == "active").all()
    for war in active_wars:
        route = (
            war.attacking_clan_id,
            war.source_territory_id,
            war.territory_id,
        )
        if route not in LEGACY_RECIPROCAL_ROUTES:
            continue
        war.status = "canceled"
        war.ended_at = now
        territory = db.get(Territory, war.territory_id)
        if territory:
            territory.attacking_clans.clear()
            territory.defending_clans.clear()
            territory.status = "owned" if territory.owner_clan_id else "neutral"
        messages.append(f"legacy reciprocal war #{war.id} canceled")
    return messages


def assign_demo_color(db, clan: Clan) -> None:
    color = DEMO_CLAN_COLORS.get(clan.id)
    if clan.map_color or not color:
        return
    color_is_used = db.query(Clan.id).filter(
        Clan.map_color == color,
        Clan.id != clan.id,
    ).first()
    if not color_is_used:
        clan.map_color = color


def set_demo_score(db, war: ClanWar, scenario: dict) -> None:
    sides = (
        (
            war.attacking_clan_id,
            scenario["attacker_points"],
            7,
            3,
        ),
        (
            war.defending_clan_id,
            scenario["defender_points"],
            3,
            7,
        ),
    )
    for clan_id, points, wins, losses in sides:
        participants = db.query(ClanWarParticipant).filter(
            ClanWarParticipant.war_id == war.id,
            ClanWarParticipant.clan_id == clan_id,
        ).order_by(ClanWarParticipant.id.asc()).all()
        if not participants:
            clan = db.get(Clan, clan_id)
            if not clan or not clan.leader_id:
                continue
            participants = [
                ClanWarParticipant(
                    war_id=war.id,
                    clan_id=clan_id,
                    user_id=clan.leader_id,
                    is_active=True,
                )
            ]
            db.add(participants[0])
        for participant in participants:
            participant.war_points = 0
            participant.wins = 0
            participant.losses = 0
        participants[0].war_points = points
        participants[0].wins = wins
        participants[0].losses = losses


def seed_wars(db) -> list[str]:
    messages = close_legacy_reciprocal_wars(db)
    service = ClanWarService()
    ownership = TerritoryOwnershipService()
    for clan_id in DEMO_CLAN_COLORS:
        clan = db.get(Clan, clan_id)
        if clan:
            assign_demo_color(db, clan)
    db.flush()

    for scenario in WAR_SCENARIOS:
        attacker = db.get(Clan, scenario["attacker_id"])
        defender = db.get(Clan, scenario["defender_id"])
        source = db.get(Territory, scenario["source_id"])
        target = db.get(Territory, scenario["target_id"])
        if not attacker or not defender or not source or not target:
            messages.append(f"war skipped: missing data {scenario}")
            continue
        ownership.transfer(
            db,
            target,
            defender.id,
            reason="demo_frontline_setup",
        )
        existing = (
            db.query(ClanWar)
            .filter(
                ClanWar.status == "active",
                ClanWar.attacking_clan_id == attacker.id,
                ClanWar.territory_id == target.id,
            )
            .first()
        )
        if existing:
            set_demo_score(db, existing, scenario)
            messages.append(f"war #{existing.id} already active: {attacker.name} -> {target.name}")
            continue
        other_attack = (
            db.query(ClanWar)
            .filter(
                ClanWar.status == "active",
                ClanWar.attacking_clan_id == attacker.id,
            )
            .first()
        )
        if other_attack:
            messages.append(f"war skipped: {attacker.name} already attacks in war #{other_attack.id}")
            continue
        leader = attacker.leader
        if not leader:
            messages.append(f"war skipped: {attacker.name} has no leader")
            continue
        attacker.next_attack_at = None
        db.commit()
        war = service.create_war(
            db,
            ClanWarCreate(
                territory_id=target.id,
                source_territory_id=source.id,
            ),
            leader,
        )
        set_demo_score(db, war, scenario)
        db.commit()
        messages.append(f"war #{war.id} created: {attacker.name} -> {target.name}")
    db.commit()
    return messages


def seed_market(db) -> list[str]:
    messages = []
    service = ClanMarketService()
    first = db.get(Clan, 1)
    second = db.get(Clan, 2)
    if not first or not second or not first.leader or not second.leader:
        return ["market skipped: demo clans or leaders are missing"]

    traveling = (
        db.query(MarketOffer)
        .filter(
            MarketOffer.status == "in_transit",
            MarketOffer.creator_clan_id == first.id,
            MarketOffer.accepted_by_clan_id == second.id,
        )
        .first()
    )
    if traveling:
        messages.append(f"traveling offer #{traveling.id} already exists")
    else:
        offer = service.create_offer(
            db,
            creator_clan_id=first.id,
            give_resource="wood",
            give_amount=4,
            receive_resource="iron",
            receive_amount=2,
            expires_in_days=7,
            current_user=first.leader,
        )
        accepted = service.accept_offer(
            db,
            offer_id=offer["id"],
            accepter_clan_id=second.id,
            current_user=second.leader,
        )
        messages.append(f"traveling offer #{accepted['id']} created")

    open_offer = (
        db.query(MarketOffer)
        .filter(
            MarketOffer.status == "open",
            MarketOffer.creator_clan_id == second.id,
            MarketOffer.give_resource == "iron",
            MarketOffer.receive_resource == "wood",
        )
        .first()
    )
    if open_offer:
        messages.append(f"open offer #{open_offer.id} already exists")
    else:
        offer = service.create_offer(
            db,
            creator_clan_id=second.id,
            give_resource="iron",
            give_amount=3,
            receive_resource="wood",
            receive_amount=5,
            expires_in_days=7,
            current_user=second.leader,
        )
        messages.append(f"open offer #{offer['id']} created")

    admin_clan = db.get(Clan, 13)
    sea_traveling = (
        db.query(MarketOffer)
        .filter(
            MarketOffer.status == "in_transit",
            MarketOffer.creator_clan_id == first.id,
            MarketOffer.accepted_by_clan_id == 13,
        )
        .first()
    )
    if sea_traveling:
        messages.append(f"sea offer #{sea_traveling.id} already exists")
    elif not admin_clan or not admin_clan.leader:
        messages.append("sea offer skipped: admin clan or leader is missing")
    else:
        offer = service.create_offer(
            db,
            creator_clan_id=first.id,
            give_resource="wood",
            give_amount=3,
            receive_resource="mithril",
            receive_amount=1,
            expires_in_days=7,
            current_user=first.leader,
        )
        accepted = service.accept_offer(
            db,
            offer_id=offer["id"],
            accepter_clan_id=admin_clan.id,
            current_user=admin_clan.leader,
        )
        messages.append(
            f"sea offer #{accepted['id']} created: "
            f"{accepted['route_mode']}, {accepted['route_steps']} steps"
        )
    return messages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        print("Dry run: add --apply to create two wars and land/sea market demo data.")
        return
    with SessionLocal() as db:
        for message in seed_wars(db) + seed_market(db):
            print(message)


if __name__ == "__main__":
    main()
