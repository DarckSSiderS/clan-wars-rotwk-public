"""Read-only projection: no emails, passwords, treasury or private messages."""

from datetime import datetime, timedelta, timezone
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from app.models.campaign import CampaignSeason, CampaignSettings
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.clan import Clan, ClanMember
from app.models.discord import DiscordLink
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar
from app.services.war_service import ClanWarService
from app.services.campaign_cycle_store import CampaignCycleStore


def iso(value):
    if value is None:
        return None
    return (
        value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    ).isoformat()


def cycle_schedule(db, season, now):
    if not season or (season.rules_snapshot or {}).get("mechanics_version") != "cycle_v1":
        return None
    row = db.query(CampaignCycleRecord).filter_by(season_id=season.id).order_by(
        CampaignCycleRecord.number.desc()).first()
    if row is None:
        return None
    timeline = CampaignCycleStore.timeline(row)
    return {
        "id": row.id,
        "number": timeline.number,
        "phase": timeline.phase_at(now).value if now >= timeline.starts_at else "scheduled",
        "preparation_at": iso(timeline.preparation_at),
        "battle_at": iso(timeline.battle_at),
        "battle_ends_at": iso(timeline.battle_ends_at),
        "replay_deadline": iso(timeline.replay_deadline),
        "next_cycle_starts_at": iso(timeline.next_cycle_starts_at),
        "season_end_requested": timeline.season_end_requested,
    }


def snapshot(db, now=None):
    now = now or datetime.now(timezone.utc)
    clans = (
        db.query(Clan)
        .filter(Clan.is_deleted.is_(False), Clan.is_admin_clan.is_(False))
        .all()
    )
    counts = dict(
        db.query(ClanMember.clan_id, func.count(ClanMember.id))
        .group_by(ClanMember.clan_id)
        .all()
    )
    territory_counts = dict(
        db.query(Territory.owner_clan_id, func.count(Territory.id))
        .group_by(Territory.owner_clan_id)
        .all()
    )
    clan_ids = {c.id for c in clans}
    memberships = {
        m.user_id: m.clan_id
        for m in db.query(ClanMember).filter(ClanMember.clan_id.in_(clan_ids)).all()
    }
    leaders = {c.id: c.leader_id for c in clans}
    identities = {}
    for link, user in (
        db.query(DiscordLink, User)
        .join(User, User.id == DiscordLink.user_id)
        .filter(User.is_active.is_(True), User.is_claimed.is_(True))
        .all()
    ):
        cid = memberships.get(user.id)
        identities[link.discord_user_id] = {
            "clan_id": cid,
            "leader": leaders.get(cid) == user.id,
        }
    wars = (
        db.query(ClanWar)
        .options(
            joinedload(ClanWar.territory),
            joinedload(ClanWar.attacking_clan),
            joinedload(ClanWar.defending_clan),
            joinedload(ClanWar.winner_clan),
        )
        .filter(
            or_(
                ClanWar.status == "active",
                ClanWar.started_at >= now - timedelta(days=7),
                ClanWar.ended_at >= now - timedelta(days=7),
            )
        )
        .order_by(ClanWar.id)
        .all()
    )
    war_service = ClanWarService()
    scores = {
        (w.id, result["clan_id"]): result["points"]
        for w in wars
        for result in war_service._get_clan_scores(db, w)
    }
    season = db.query(CampaignSeason).filter_by(status="active").first()
    settings = db.get(CampaignSettings, 1)
    hall = (
        db.query(CampaignSeason)
        .filter(CampaignSeason.status != "active")
        .options(joinedload(CampaignSeason.results))
        .order_by(CampaignSeason.number.desc())
        .limit(3)
        .all()
    )
    return {
        "season": season.name if season else None,
        "cycle": cycle_schedule(db, season, now),
        "paused": bool(settings and settings.is_paused),
        "clans": sorted(
            [
                {
                    "id": c.id,
                    "name": c.name,
                    "motto": c.motto or "",
                    "color": c.map_color,
                    "level": c.level,
                    "members": counts.get(c.id, 0),
                    "capacity": c.max_members,
                    "recruiting": c.is_recruiting,
                    "territories": territory_counts.get(c.id, 0),
                    "influence": c.territory_points or 0,
                }
                for c in clans
            ],
            key=lambda c: (-c["influence"], c["id"]),
        ),
        "identities": identities,
        "wars": [
            {
                "id": w.id,
                "territory": (
                    w.territory.name if w.territory else "Удалённая территория"
                ),
                "attacker_id": w.attacking_clan_id,
                "defender_id": w.defending_clan_id,
                "attacker": (
                    w.attacking_clan.name if w.attacking_clan else "Удалённый клан"
                ),
                "defender": (
                    w.defending_clan.name if w.defending_clan else "Нейтральная земля"
                ),
                "winner": w.winner_clan.name if w.winner_clan else "Нет победителя",
                "status": w.status,
                "attacker_score": scores.get((w.id, w.attacking_clan_id), 0),
                "defender_score": scores.get((w.id, w.defending_clan_id), 0),
                "started_at": iso(w.started_at),
                "ends_at": iso(w.ends_at),
                "ended_at": iso(w.ended_at),
            }
            for w in wars
        ],
        "hall": [
            {
                "name": s.name,
                "results": [
                    {
                        "name": r.clan_name,
                        "rank": r.rank,
                        "territories": r.territory_count,
                    }
                    for r in s.results[:5]
                ],
            }
            for s in hall
        ],
    }
