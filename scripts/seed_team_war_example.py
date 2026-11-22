"""Создаёт одну тестовую войну из настоящего командного replay."""

import argparse
import sys
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import func

from app.core.time import as_utc, utc_now
from app.database import SessionLocal
from app.models.clan import Clan, ClanMembershipPeriod
from app.models.match import Match
from app.models.territory import Territory
from app.models.war import ClanWar, ClanWarMatchResult
from app.services.elo_service import PATCH_ALL
from app.services.war_service import ClanWarService, PROTECTED_TERRITORY_NAMES


TEAM_MODES = ("4 versus 4", "3 versus 3", "2 versus 2")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--attacker", required=True, help="Название атакующего клана")
    parser.add_argument("--defender", required=True, help="Название защищающегося клана")
    return parser.parse_args()


def clan_by_name(db, name: str) -> Clan:
    clan = db.query(Clan).filter(func.lower(Clan.name) == name.casefold()).first()
    if clan is None or clan.is_admin_clan:
        raise RuntimeError(f"Обычный клан не найден: {name}")
    return clan


def run(attacker_name: str, defender_name: str):
    with SessionLocal() as db:
        service = ClanWarService()
        attacker = clan_by_name(db, attacker_name)
        defender = clan_by_name(db, defender_name)
        now = utc_now()

        matches = (
            db.query(Match)
            .filter(
                Match.gamemode_name.in_(TEAM_MODES),
                Match.match_date >= now - timedelta(days=3),
                Match.participants.any(),
            )
            .order_by(Match.match_date.desc())
            .all()
        )

        selected = None
        selected_users = None
        from app.models.user import User

        for mode in TEAM_MODES:
            for match in matches:
                if (match.gamemode_name or match.game_mode) != mode:
                    continue
                if db.query(ClanWarMatchResult.id).filter(
                    ClanWarMatchResult.match_id == match.id,
                ).first():
                    continue
                names = [item.nickname for item in match.participants if not item.is_observer]
                users = db.query(User).filter(User.username.in_(names)).all()
                users_by_name = {user.username.casefold(): user for user in users}
                if len(users_by_name) != len({name.casefold() for name in names}):
                    continue
                played_at = as_utc(match.match_date)
                conflict = any(
                    service.membership_history.clan_ids_at(db, user.id, played_at)
                    for user in users
                )
                if conflict:
                    continue
                selected = match
                selected_users = users_by_name
                break
            if selected:
                break

        if selected is None:
            raise RuntimeError("Нет свободного командного replay за последние трое суток")

        active_territory_ids = {
            row[0]
            for row in db.query(ClanWar.territory_id).filter(ClanWar.status == "active").all()
        }
        target = (
            db.query(Territory)
            .filter(
                Territory.owner_clan_id == defender.id,
                Territory.is_playable.is_(True),
                ~Territory.id.in_(active_territory_ids or {-1}),
                ~Territory.name.in_(PROTECTED_TERRITORY_NAMES),
            )
            .order_by(Territory.id)
            .first()
        )
        if target is None:
            raise RuntimeError("У защищающегося клана нет свободной территории для примера")
        source = (
            db.query(Territory)
            .filter(Territory.owner_clan_id == attacker.id)
            .order_by(Territory.id)
            .first()
        )

        played_at = as_utc(selected.match_date)
        for participant in selected.participants:
            if participant.is_observer:
                continue
            user = selected_users[participant.nickname.casefold()]
            clan_id = attacker.id if participant.is_winner else defender.id
            db.add(ClanMembershipPeriod(
                user_id=user.id,
                clan_id=clan_id,
                started_at=played_at - timedelta(minutes=5),
                ended_at=played_at + timedelta(minutes=5),
                started_reason="team_war_demo",
                ended_reason="team_war_demo",
            ))
            for identity in user.external_identities:
                identity.verification_status = "verified"
                identity.verified_at = identity.verified_at or now

        war = ClanWar(
            territory_id=target.id,
            source_territory_id=source.id if source else None,
            attacking_clan_id=attacker.id,
            defending_clan_id=defender.id,
            war_type="territory_attack",
            status="active",
            started_at=played_at - timedelta(hours=1),
            ends_at=played_at - timedelta(hours=1) + timedelta(days=4),
            attacker_power=0,
            defender_power=0,
            influence_cost=0,
            attack_route="land",
            attacker_patch=PATCH_ALL,
            defender_patch=PATCH_ALL,
            scoring_version="elo_team_v2",
        )
        db.add(war)
        db.commit()
        service.record_match_result(
            db,
            selected.winner_player,
            selected.loser_player,
            selected.match_date,
            match=selected,
        )
        print(
            f"Создана война #{war.id}: {selected.gamemode_name}, "
            f"{attacker.name} -> {defender.name}, территория {target.name}"
        )


if __name__ == "__main__":
    arguments = parse_args()
    run(arguments.attacker, arguments.defender)
