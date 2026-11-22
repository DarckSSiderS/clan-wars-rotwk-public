"""Fill clans in active wars with the most active free ladder profiles."""

import argparse
import json

from sqlalchemy import func, select, union_all

from app.core.time import utc_now
from app.database import SessionLocal
from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.external_identity import ExternalPlayerIdentity
from app.models.match import Match
from app.models.user import User
from app.models.war import ClanWar
from app.services.operation_service import AdminAuditService


def build_candidates(db):
    player_names = union_all(
        select(Match.winner_player.label("username")),
        select(Match.loser_player.label("username")),
    ).subquery()
    activity = (
        select(
            player_names.c.username,
            func.count().label("match_count"),
        )
        .group_by(player_names.c.username)
        .subquery()
    )
    return (
        db.query(User, activity.c.match_count)
        .join(activity, activity.c.username == User.username)
        .outerjoin(ClanMember, ClanMember.user_id == User.id)
        .filter(
            ClanMember.id.is_(None),
            User.is_active.is_(True),
        )
        .order_by(activity.c.match_count.desc(), User.username.asc())
        .all()
    )


def plan_assignments(db, target_size: int, include_unverified: bool):
    wars = (
        db.query(ClanWar)
        .filter(ClanWar.status == "active")
        .order_by(ClanWar.started_at.asc(), ClanWar.id.asc())
        .all()
    )
    clan_ids = []
    for war in wars:
        for clan_id in (war.attacking_clan_id, war.defending_clan_id):
            if clan_id and clan_id not in clan_ids:
                clan_ids.append(clan_id)

    clans = {
        clan.id: clan
        for clan in db.query(Clan).filter(Clan.id.in_(clan_ids)).all()
    } if clan_ids else {}
    candidates = []
    skipped_by_status = {}
    for user, match_count in build_candidates(db):
        status = user.external_identity_status or "missing"
        if status == "missing":
            skipped_by_status[status] = skipped_by_status.get(status, 0) + 1
            continue
        if status != "verified" and not include_unverified:
            skipped_by_status[status] = skipped_by_status.get(status, 0) + 1
            continue
        candidates.append(
            {
                "user": user,
                "match_count": int(match_count or 0),
                "verification_status": status,
            }
        )

    assignments = []
    candidate_index = 0
    clan_summaries = []
    for clan_id in clan_ids:
        clan = clans.get(clan_id)
        if clan is None or clan.is_admin_clan:
            continue
        existing_count = (
            db.query(ClanMember)
            .filter(ClanMember.clan_id == clan_id)
            .count()
        )
        desired_count = min(target_size, clan.max_members or target_size)
        missing_count = max(0, desired_count - existing_count)
        selected = candidates[candidate_index:candidate_index + missing_count]
        candidate_index += len(selected)
        for candidate in selected:
            assignments.append(
                {
                    "clan": clan,
                    **candidate,
                }
            )
        clan_summaries.append(
            {
                "clan_id": clan.id,
                "clan_name": clan.name,
                "current_members": existing_count,
                "planned_members": len(selected),
                "target_members": desired_count,
            }
        )

    return wars, clan_summaries, assignments, skipped_by_status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--target-size", type=int, default=6)
    parser.add_argument("--actor", default="darcks")
    parser.add_argument("--include-unverified", action="store_true")
    parser.add_argument("--verify-for-test", action="store_true")
    args = parser.parse_args()

    if args.target_size < 5 or args.target_size > 7:
        raise SystemExit("--target-size must be between 5 and 7")
    if args.verify_for_test and not args.include_unverified:
        raise SystemExit("--verify-for-test requires --include-unverified")

    db = SessionLocal()
    try:
        wars, clan_summaries, assignments, skipped = plan_assignments(
            db,
            args.target_size,
            args.include_unverified,
        )
        result = {
            "mode": "apply" if args.apply else "dry-run",
            "active_wars": len(wars),
            "clans": clan_summaries,
            "assignments": [
                {
                    "clan_id": item["clan"].id,
                    "clan_name": item["clan"].name,
                    "user_id": item["user"].id,
                    "username": item["user"].username,
                    "matches": item["match_count"],
                    "verification_status": item["verification_status"],
                }
                for item in assignments
            ],
            "skipped_free_profiles_by_status": skipped,
        }
        if not args.apply:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        actor = db.query(User).filter(User.username == args.actor).first()
        if actor is None:
            raise SystemExit(f"Admin actor not found: {args.actor}")

        joined_at = utc_now()
        applied = []
        for item in assignments:
            user = item["user"]
            clan = item["clan"]
            if db.query(ClanMember).filter(ClanMember.user_id == user.id).first():
                continue
            member = ClanMember(
                user_id=user.id,
                clan_id=clan.id,
                rank="Воин",
                is_trader=False,
                joined_at=joined_at,
            )
            db.add(member)
            db.flush()
            db.add(
                ClanMembershipPeriod(
                    user_id=user.id,
                    clan_id=clan.id,
                    started_at=joined_at,
                    started_reason="admin_live_war_test",
                )
            )
            if item["verification_status"] != "verified":
                if not args.verify_for_test:
                    raise RuntimeError(
                        f"{user.username} is not verified; use --verify-for-test"
                    )
                identity = (
                    db.query(ExternalPlayerIdentity)
                    .filter(
                        ExternalPlayerIdentity.user_id == user.id,
                        ExternalPlayerIdentity.source == "bfmeladder",
                    )
                    .one()
                )
                previous_status = identity.verification_status
                identity.verification_status = "verified"
                identity.verified_at = joined_at
                AdminAuditService().record(
                    db,
                    actor_user_id=actor.id,
                    action="external_identity_verified_for_live_war_test",
                    entity_type="external_player_identity",
                    entity_id=identity.id,
                    before_data={"verification_status": previous_status},
                    after_data={
                        "verification_status": "verified",
                        "external_uuid": identity.external_uuid,
                        "username": user.username,
                    },
                    reason="Временное подтверждение ladder-профиля для живого теста войны",
                )
            AdminAuditService().record(
                db,
                actor_user_id=actor.id,
                action="active_war_test_member_added",
                entity_type="clan_member",
                entity_id=member.id,
                after_data={
                    "clan_id": clan.id,
                    "clan_name": clan.name,
                    "user_id": user.id,
                    "username": user.username,
                    "match_count": item["match_count"],
                    "verification_status": item["verification_status"],
                    "joined_at": joined_at.isoformat(),
                },
                reason="Наполнение активной войны частыми игроками для живого теста",
            )
            applied.append(user.username)

        db.commit()
        result["applied_users"] = applied
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
