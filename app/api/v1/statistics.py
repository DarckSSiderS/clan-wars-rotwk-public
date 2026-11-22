import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, and_, or_, literal, case
from sqlalchemy.orm import Session

from app.config import settings
from app.core.auth import get_current_active_user
from app.core.factions import build_patch_faction_statistics
from app.core.time import as_utc, utc_now
from app.database import get_db
from app.models.campaign import CampaignSeason
from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.external_identity import ExternalPlayerAlias, ExternalPlayerIdentity
from app.models.match import Match, MatchParticipant
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.models.user import User
from app.models.user import User as UserModel
from app.models.war import ClanWar
from app.services.ladder_service import ladder_service
from app.services.map_preview_storage_service import MapPreviewStorageService
from app.services.replay_storage_service import ReplayStorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/statistics", tags=["statistics"])

LIVE_CACHE_TTL = 600
_live_cache = {"matches": [], "updated_at": None, "expires_at": 0.0}
_live_cache_lock = asyncio.Lock()
map_preview_storage = MapPreviewStorageService()


def _match_by_reference(db: Session, match_ref: str) -> Match:
    match = db.query(Match).filter(Match.match_id == str(match_ref)).first()
    if match is None and str(match_ref).isdigit():
        match = db.get(Match, int(match_ref))
    if match is None:
        raise HTTPException(status_code=404, detail="Матч не найден")
    return match


def _json_items(value) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _match_detail_payload(match: Match) -> dict:
    from app.services.elo_service import is_unverified_rating
    storage = ReplayStorageService()
    participants = [
        {
            "id": participant.id,
            "username": participant.nickname,
            "player_uuid": participant.player_uuid,
            "faction": participant.faction,
            "faction_index": participant.faction_index,
            "team": participant.team,
            "is_winner": bool(participant.is_winner),
            "is_observer": bool(participant.is_observer),
            "elo": participant.elo,
            "old_rank": participant.old_rank,
            "new_rank": participant.new_rank,
        }
        for participant in match.participants or []
    ]
    if not participants:
        participants = [
            {
                "username": match.winner_player,
                "player_uuid": match.winner_player_uuid,
                "faction": match.winner_faction,
                "faction_index": match.winner_faction_index,
                "team": 1,
                "is_winner": True,
                "is_observer": False,
                "elo": match.winner_elo,
                "old_rank": match.winner_old_rank,
                "new_rank": match.winner_new_rank,
            },
            {
                "username": match.loser_player,
                "player_uuid": match.loser_player_uuid,
                "faction": match.loser_faction,
                "faction_index": match.loser_faction_index,
                "team": 2,
                "is_winner": False,
                "is_observer": False,
                "elo": match.loser_elo,
                "old_rank": match.loser_old_rank,
                "new_rank": match.loser_new_rank,
            },
        ]

    for participant in participants:
        participant['elo_is_verified'] = participant['elo'] is not None and not is_unverified_rating(
            match, participant.get('player_uuid'), participant['username']
        )
    replay_supported = storage.is_supported(match)
    replay_path = Path(match.replay_local_path).resolve() if match.replay_local_path else None
    return {
        "id": match.id,
        "match_id": match.match_id,
        "winner_player": match.winner_player,
        "winner_faction": match.winner_faction,
        "loser_player": match.loser_player,
        "loser_faction": match.loser_faction,
        "match_date": match.match_date.isoformat(),
        "duration": match.duration,
        "map_name": match.map_name,
        "map_id": match.map_id,
        "map_preview_url": map_preview_storage.public_url(match.map_name),
        "game_mode": match.gamemode_name or match.game_mode,
        "game_name": match.game_name,
        "arena_id": match.arena_id,
        "patch_id": match.patch_id,
        "patch_name": match.patch_name or match.patch_version,
        "patch_version": match.patch_version,
        "rating_patch_family": match.rating_patch_family,
        "rating_warning": bool((match.source_payload or {}).get('rating_unverified_players')) or match.rating_source == 'bfmeladder_rating_incomplete',
        "elo_delta": match.elo_delta,
        "downloads": match.downloads,
        "likes": _json_items(match.likes),
        "comments": _json_items(match.comments),
        "is_valid": match.is_valid,
        "is_qualification_round": match.is_qualification_round,
        "participants": participants,
        "replay_supported": replay_supported,
        "replay_archived": bool(replay_path and replay_path.is_file()),
        "replay_file_size": match.replay_file_size,
        "replay_download_url": (
            f"/api/v1/statistics/matches/{match.match_id}/replay"
            if replay_supported else None
        ),
    }


def _registered_player_count(db: Session) -> int:
    return (
        db.query(func.count(User.id))
        .filter(User.is_claimed.is_(True))
        .scalar()
        or 0
    )


@router.get("/home")
def get_home_statistics(db: Session = Depends(get_db)):
    active_season = (
        db.query(CampaignSeason)
        .filter(CampaignSeason.status == "active")
        .order_by(CampaignSeason.starts_at.desc(), CampaignSeason.id.desc())
        .first()
    )
    clan_player_count = (
        db.query(func.count(func.distinct(ClanMember.user_id)))
        .join(Clan, Clan.id == ClanMember.clan_id)
        .filter(
            Clan.is_admin_clan.is_(False),
            Clan.is_deleted.is_(False),
        )
        .scalar()
        or 0
    )
    clan_rows = (
        db.query(
            Clan.id,
            Clan.name,
            Clan.avatar_url,
            Clan.territory_points,
            func.count(ClanMember.id).label("member_count"),
        )
        .join(ClanMember, ClanMember.clan_id == Clan.id)
        .filter(
            Clan.is_admin_clan.is_(False),
            Clan.is_deleted.is_(False),
        )
        .group_by(
            Clan.id,
            Clan.name,
            Clan.avatar_url,
            Clan.territory_points,
        )
        .order_by(
            Clan.territory_points.desc(),
            func.count(ClanMember.id).desc(),
            Clan.name.asc(),
        )
        .all()
    )
    territory_rows = (
        db.query(
            func.count(Territory.id).label("total"),
            func.sum(case((Territory.owner_clan_id.isnot(None), 1), else_=0)).label("occupied"),
            func.sum(case((Territory.status == "contested", 1), else_=0)).label("contested"),
            func.sum(case((Territory.owner_clan_id.is_(None), 1), else_=0)).label("free"),
        )
        .filter(Territory.is_playable.is_(True))
        .one()
    )
    active_wars = (
        db.query(ClanWar)
        .filter(ClanWar.status == "active")
        .order_by(ClanWar.ends_at.asc(), ClanWar.id.asc())
        .all()
    )
    recent_territory_changes = (
        db.query(TerritoryOwnershipHistory)
        .join(Territory, Territory.id == TerritoryOwnershipHistory.territory_id)
        .join(Clan, Clan.id == TerritoryOwnershipHistory.clan_id)
        .filter(
            TerritoryOwnershipHistory.war_id.isnot(None),
            Territory.is_playable.is_(True),
            Clan.is_admin_clan.is_(False),
        )
        .order_by(
            TerritoryOwnershipHistory.started_at.desc(),
            TerritoryOwnershipHistory.id.desc(),
        )
        .limit(5)
        .all()
    )

    def clan_summary(clan):
        if clan is None:
            return None
        return {
            "id": clan.id,
            "name": clan.name,
            "avatar_url": clan.avatar_url,
            "map_color": clan.map_color,
        }

    season_summary = None
    if active_season is not None:
        starts_at = as_utc(active_season.starts_at)
        ends_at = as_utc(active_season.ends_at)
        progress_percent = None
        if starts_at and ends_at and ends_at > starts_at:
            elapsed = (utc_now() - starts_at).total_seconds()
            duration = (ends_at - starts_at).total_seconds()
            progress_percent = round(max(0, min(100, elapsed / duration * 100)))
        season_summary = {
            "id": active_season.id,
            "number": active_season.number,
            "name": active_season.name,
            "status": active_season.status,
            "starts_at": starts_at.isoformat() if starts_at else None,
            "ends_at": ends_at.isoformat() if ends_at else None,
            "progress_percent": progress_percent,
            "goals": [
                {
                    "key": "territories_controlled",
                    "current": int(territory_rows.occupied or 0),
                    "target": int(territory_rows.total or 0),
                },
                {
                    "key": "active_wars",
                    "current": len(active_wars),
                    "target": None,
                },
                {
                    "key": "campaign_clans",
                    "current": len(clan_rows),
                    "target": None,
                },
            ],
        }

    return {
        "season": season_summary,
        "clan_players": int(clan_player_count),
        "total_clans": len(clan_rows),
        "territories": {
            "total": int(territory_rows.total or 0),
            "occupied": int(territory_rows.occupied or 0),
            "contested": int(territory_rows.contested or 0),
            "free": int(territory_rows.free or 0),
        },
        "active_wars": [
            {
                "id": war.id,
                "territory_id": war.territory_id,
                "territory_name": war.territory.name,
                "territory_svg_path_data": war.territory.svg_path_data,
                "started_at": as_utc(war.started_at).isoformat() if war.started_at else None,
                "ends_at": as_utc(war.ends_at).isoformat() if war.ends_at else None,
                "attack_route": war.attack_route,
                "attacking_clan": clan_summary(war.attacking_clan),
                "defending_clan": clan_summary(war.defending_clan),
            }
            for war in active_wars
        ],
        "recent_territory_changes": [
            {
                "territory_id": change.territory_id,
                "territory_name": change.territory.name,
                "territory_svg_path_data": change.territory.svg_path_data,
                "clan_id": change.clan_id,
                "clan_name": change.clan.name,
                "clan_avatar_url": change.clan.avatar_url,
                "clan_map_color": change.clan.map_color,
                "captured_at": as_utc(change.started_at).isoformat(),
                "war_id": change.war_id,
            }
            for change in recent_territory_changes
        ],
        "top_clans": [
            {
                "id": row.id,
                "name": row.name,
                "avatar_url": row.avatar_url,
                "territory_points": row.territory_points or 0,
                "member_count": row.member_count,
            }
            for row in clan_rows[:5]
        ],
    }

@router.get("/overall")
async def get_overall_statistics(
    period: str = "30d",
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Возвращает сводные данные для раздела статистики."""
    try:
        today = datetime.now().date()
        activity_start = datetime.combine(
            today - timedelta(days=29),
            datetime.min.time(),
        )
        period_key = period if period in {"30d", "season", "all"} else "30d"
        period_start = activity_start
        if period_key == "all":
            period_start = None
        elif period_key == "season":
            active_season = (
                db.query(CampaignSeason)
                .filter(CampaignSeason.status == "active")
                .order_by(CampaignSeason.starts_at.desc(), CampaignSeason.id.desc())
                .first()
            )
            period_start = active_season.starts_at if active_season else activity_start

        total_matches_query = db.query(func.count(Match.id))
        if period_start is not None:
            total_matches_query = total_matches_query.filter(Match.match_date >= period_start)
        total_matches = total_matches_query.scalar() or 0
        unique_players = _registered_player_count(db)
        total_clans = (
            db.query(func.count(Clan.id))
            .filter(
                Clan.is_admin_clan.is_(False),
                Clan.is_deleted.is_(False),
            )
            .scalar()
            or 0
        )

        daily_rows = (
            db.query(
                func.date(Match.match_date).label("match_day"),
                func.count(Match.id).label("match_count"),
            )
            .filter(Match.match_date >= activity_start)
            .group_by(func.date(Match.match_date))
            .all()
        )
        daily_counts = {
            str(match_day): int(match_count)
            for match_day, match_count in daily_rows
        }
        matches_today = daily_counts.get(today.isoformat(), 0)

        capture_rows = (
            db.query(
                func.date(TerritoryOwnershipHistory.started_at).label("capture_day"),
                func.count(TerritoryOwnershipHistory.id).label("capture_count"),
            )
            .filter(
                TerritoryOwnershipHistory.started_at >= activity_start,
                TerritoryOwnershipHistory.reason == "capture",
            )
            .group_by(func.date(TerritoryOwnershipHistory.started_at))
            .all()
        )
        daily_capture_counts = {
            str(capture_day): int(capture_count)
            for capture_day, capture_count in capture_rows
        }
        total_captures_query = db.query(func.count(TerritoryOwnershipHistory.id)).filter(
            TerritoryOwnershipHistory.reason == "capture"
        )
        if period_start is not None:
            total_captures_query = total_captures_query.filter(
                TerritoryOwnershipHistory.started_at >= period_start
            )
        total_captures = total_captures_query.scalar() or 0
        territory_total = (
            db.query(func.count(Territory.id))
            .filter(Territory.is_playable.is_(True))
            .scalar()
            or 0
        )
        territory_control_rows = (
            db.query(
                Clan.id,
                Clan.name,
                Clan.map_color,
                func.count(Territory.id).label("territory_count"),
            )
            .join(Territory, Territory.owner_clan_id == Clan.id)
            .filter(
                Clan.is_admin_clan.is_(False),
                Territory.is_playable.is_(True),
            )
            .group_by(Clan.id, Clan.name, Clan.map_color)
            .order_by(func.count(Territory.id).desc(), Clan.name.asc())
            .all()
        )

        participant_factions = (
            db.query(
                MatchParticipant.faction,
                func.count(MatchParticipant.id).label("count"),
            )
            .filter(
                MatchParticipant.faction.isnot(None),
                MatchParticipant.is_observer.is_(False),
            )
            .group_by(MatchParticipant.faction)
            .all()
        )
        winner_factions = (
            db.query(
                Match.winner_faction,
                func.count(Match.id).label("count"),
            )
            .filter(Match.winner_faction.isnot(None), ~Match.participants.any())
            .group_by(Match.winner_faction)
            .all()
        )
        loser_factions = (
            db.query(
                Match.loser_faction,
                func.count(Match.id).label("count"),
            )
            .filter(Match.loser_faction.isnot(None), ~Match.participants.any())
            .group_by(Match.loser_faction)
            .all()
        )

        participant_patch_factions = (
            db.query(
                Match.rating_patch_family,
                MatchParticipant.faction,
                func.count(MatchParticipant.id).label("count"),
            )
            .join(Match, Match.id == MatchParticipant.match_id)
            .filter(
                Match.rating_patch_family.in_(("ennorath", "patch_202")),
                MatchParticipant.faction.isnot(None),
                MatchParticipant.is_observer.is_(False),
            )
            .group_by(Match.rating_patch_family, MatchParticipant.faction)
            .all()
        )
        legacy_winner_patch_factions = (
            db.query(
                Match.rating_patch_family,
                Match.winner_faction,
                func.count(Match.id).label("count"),
            )
            .filter(
                Match.rating_patch_family.in_(("ennorath", "patch_202")),
                Match.winner_faction.isnot(None),
                ~Match.participants.any(),
            )
            .group_by(Match.rating_patch_family, Match.winner_faction)
            .all()
        )
        legacy_loser_patch_factions = (
            db.query(
                Match.rating_patch_family,
                Match.loser_faction,
                func.count(Match.id).label("count"),
            )
            .filter(
                Match.rating_patch_family.in_(("ennorath", "patch_202")),
                Match.loser_faction.isnot(None),
                ~Match.participants.any(),
            )
            .group_by(Match.rating_patch_family, Match.loser_faction)
            .all()
        )
        popular_factions_by_patch = build_patch_faction_statistics(
            [
                *participant_patch_factions,
                *legacy_winner_patch_factions,
                *legacy_loser_patch_factions,
            ]
        )

        faction_stats = {}
        for faction, count in participant_factions:
            faction_stats[faction] = faction_stats.get(faction, 0) + count
        for faction, count in winner_factions:
            faction_stats[faction] = faction_stats.get(faction, 0) + count
        for faction, count in loser_factions:
            faction_stats[faction] = faction_stats.get(faction, 0) + count
        popular_factions = sorted(faction_stats.items(), key=lambda x: x[1], reverse=True)[:5]
        daily_activity = [
            {
                "date": day.strftime("%d.%m"),
                "matches": daily_counts.get(day.isoformat(), 0),
            }
            for day in (
                today - timedelta(days=offset)
                for offset in range(29, -1, -1)
            )
        ]
        daily_captures = [
            {
                "date": day.strftime("%d.%m"),
                "captures": daily_capture_counts.get(day.isoformat(), 0),
            }
            for day in (
                today - timedelta(days=offset)
                for offset in range(29, -1, -1)
            )
        ]
        occupied_territories = sum(row.territory_count for row in territory_control_rows)

        return {
            "period": period_key,
            "period_start": period_start.isoformat() if period_start else None,
            "total_matches": total_matches,
            "total_players": unique_players,
            "total_clans": total_clans,
            "matches_today": matches_today,
            "total_captures": int(total_captures),
            "territories": {
                "total": int(territory_total),
                "occupied": int(occupied_territories),
                "free": max(0, int(territory_total) - int(occupied_territories)),
            },
            "territory_control": [
                {
                    "clan_id": row.id,
                    "clan_name": row.name,
                    "map_color": row.map_color,
                    "territories": int(row.territory_count),
                    "percent": round(
                        int(row.territory_count) / int(territory_total) * 100,
                        1,
                    ) if territory_total else 0,
                }
                for row in territory_control_rows
            ],
            "popular_factions": [{"faction": faction, "count": count} for faction, count in popular_factions],
            "popular_factions_by_patch": popular_factions_by_patch,
            "daily_activity": daily_activity,
            "daily_captures": daily_captures,
        }
    except Exception as e:
        logger.error(f"Ошибка получения общей статистики: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения статистики")

@router.get("/clans")
async def get_clan_statistics(
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Возвращает статистику кланов без отдельных запросов для каждого игрока."""
    try:
        clans = (
            db.query(Clan)
            .filter(
                Clan.is_admin_clan.is_(False),
                Clan.is_deleted.is_(False),
            )
            .all()
        )
        member_rows = (
            db.query(
                ClanMember.clan_id,
                ClanMember.user_id,
                User.username,
            )
            .join(User, User.id == ClanMember.user_id)
            .all()
        )
        members_by_clan = defaultdict(list)
        for clan_id, user_id, username in member_rows:
            if username:
                members_by_clan[clan_id].append(
                    {
                        "user_id": user_id,
                        "username": username,
                    }
                )

        totals_by_clan = defaultdict(lambda: {"wins": 0, "losses": 0})
        if members_by_clan:
            membership_windows = (
                db.query(
                    ClanMember.clan_id.label("clan_id"),
                    User.username.label("username"),
                    ExternalPlayerIdentity.external_uuid.label('player_uuid'),
                    ExternalPlayerIdentity.current_nickname.label('current_nickname'),
                    func.coalesce(
                        ClanMembershipPeriod.started_at,
                        ClanMember.joined_at,
                    ).label("started_at"),
                    ClanMembershipPeriod.ended_at.label("ended_at"),
                )
                .join(User, User.id == ClanMember.user_id)
                .outerjoin(ExternalPlayerIdentity, and_(
                    ExternalPlayerIdentity.user_id == User.id,
                    ExternalPlayerIdentity.source == 'bfmeladder',
                ))
                .outerjoin(
                    ClanMembershipPeriod,
                    and_(
                        ClanMembershipPeriod.clan_id == ClanMember.clan_id,
                        ClanMembershipPeriod.user_id == ClanMember.user_id,
                    ),
                )
                .filter(User.username.isnot(None))
                .subquery()
            )
            membership_window_filter = and_(
                Match.match_date >= membership_windows.c.started_at,
                or_(
                    membership_windows.c.ended_at.is_(None),
                    Match.match_date < membership_windows.c.ended_at,
                ),
            )
            def member_identity(name, uuid):
                return or_(uuid == membership_windows.c.player_uuid,
                    and_(or_(uuid.is_(None), uuid == ''), or_(
                        func.lower(func.trim(name)) == func.lower(membership_windows.c.username),
                        func.lower(func.trim(name)) == func.lower(membership_windows.c.current_nickname),
                    )))
            participant_results = (
                db.query(
                    membership_windows.c.clan_id.label("clan_id"),
                    MatchParticipant.is_winner.label("is_winner"),
                    func.count(MatchParticipant.id).label("matches_count"),
                )
                .join(
                    MatchParticipant,
                    member_identity(MatchParticipant.nickname, MatchParticipant.player_uuid),
                )
                .join(Match, Match.id == MatchParticipant.match_id)
                .filter(
                    MatchParticipant.is_observer.is_(False),
                    membership_window_filter,
                )
                .group_by(
                    membership_windows.c.clan_id,
                    MatchParticipant.is_winner,
                )
            )
            legacy_winners = (
                db.query(
                    membership_windows.c.clan_id.label("clan_id"),
                    literal(True).label("is_winner"),
                    func.count(Match.id).label("matches_count"),
                )
                .join(Match, member_identity(Match.winner_player, Match.winner_player_uuid))
                .filter(
                    ~Match.participants.any(),
                    membership_window_filter,
                )
                .group_by(membership_windows.c.clan_id)
            )
            legacy_losers = (
                db.query(
                    membership_windows.c.clan_id.label("clan_id"),
                    literal(False).label("is_winner"),
                    func.count(Match.id).label("matches_count"),
                )
                .join(Match, member_identity(Match.loser_player, Match.loser_player_uuid))
                .filter(
                    ~Match.participants.any(),
                    membership_window_filter,
                )
                .group_by(membership_windows.c.clan_id)
            )
            membership_results = participant_results.union_all(
                legacy_winners,
                legacy_losers,
            ).all()

            for clan_id, is_winner, matches_count in membership_results:
                result_key = "wins" if is_winner else "losses"
                totals_by_clan[clan_id][result_key] += matches_count

        territory_counts = dict(
            db.query(
                Territory.owner_clan_id,
                func.count(Territory.id),
            )
            .filter(Territory.owner_clan_id.isnot(None))
            .group_by(Territory.owner_clan_id)
            .all()
        )
        war_totals = defaultdict(
            lambda: {
                "wars_won": 0,
                "wars_lost": 0,
                "defenses_won": 0,
            }
        )
        completed_wars = (
            db.query(
                ClanWar.attacking_clan_id,
                ClanWar.defending_clan_id,
                ClanWar.winner_clan_id,
            )
            .filter(ClanWar.status == "completed")
            .all()
        )
        for attacker_id, defender_id, winner_id in completed_wars:
            if not winner_id:
                continue
            war_totals[winner_id]["wars_won"] += 1
            if defender_id and winner_id == defender_id:
                war_totals[defender_id]["defenses_won"] += 1
            for participant_id in (attacker_id, defender_id):
                if participant_id and participant_id != winner_id:
                    war_totals[participant_id]["wars_lost"] += 1

        clan_stats = []
        for clan in clans:
            members = members_by_clan.get(clan.id, [])
            if not members:
                continue

            wins = totals_by_clan[clan.id]["wins"]
            losses = totals_by_clan[clan.id]["losses"]
            total_matches = wins + losses
            win_rate = round((wins / total_matches * 100), 1) if total_matches else 0

            clan_stats.append({
                "id": clan.id,
                "name": clan.name or f"Клан #{clan.id}",
                "logo_url": clan.avatar_url,
                "member_count": len(members),
                "wins": wins,
                "losses": losses,
                "total_matches": total_matches,
                "win_rate": win_rate,
                "influence": clan.territory_points or 0,
                "territory_count": territory_counts.get(clan.id, 0),
                "defenses_won": war_totals[clan.id]["defenses_won"],
                "wars_won": war_totals[clan.id]["wars_won"],
                "wars_lost": war_totals[clan.id]["wars_lost"],
            })

        clan_stats.sort(
            key=lambda item: (
                item["influence"],
                item["territory_count"],
                item["defenses_won"],
                item["member_count"],
            ),
            reverse=True,
        )
        return {"clans": clan_stats}
    except Exception as e:
        logger.error(f"Ошибка получения статистики кланов: {e}")
        logger.error(f"Тип ошибки: {type(e).__name__}")
        logger.error(f"Детали ошибки: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка получения статистики кланов")


@router.get("/players")
async def get_player_ratings(
    patch: str = Query("ennorath"),
    sort: str = Query("elo_desc"),
    search: str = Query(None),
    min_elo: int = Query(None, ge=0),
    max_elo: int = Query(None, ge=0),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Возвращает последний Elo игрока отдельно для каждого поддерживаемого мода."""
    patch_family = patch if patch in {"ennorath", "patch_202"} else "ennorath"
    from app.services.arena_current_rating_service import arena_current_ratings
    from app.services.elo_service import is_unverified_rating
    from types import SimpleNamespace
    player_key = func.coalesce(
        func.nullif(MatchParticipant.player_uuid, ''),
        'name:' + func.lower(func.trim(MatchParticipant.nickname)),
    )
    captured_at = func.coalesce(Match.ratings_captured_at, Match.match_date, Match.created_at)

    ranked_snapshots = (
        db.query(
            player_key.label("player_key"),
            MatchParticipant.nickname.label("nickname"),
            MatchParticipant.player_uuid.label("player_uuid"),
            Match.source_payload.label('source_payload'),
            MatchParticipant.elo.label("elo"),
            captured_at.label("captured_at"),
            func.row_number().over(
                partition_by=player_key,
                order_by=(captured_at.desc(), Match.id.desc()),
            ).label("snapshot_number"),
        )
        .join(Match, Match.id == MatchParticipant.match_id)
        .filter(
            Match.rating_patch_family == patch_family,
            MatchParticipant.elo.isnot(None),
            MatchParticipant.is_observer.is_(False),
        )
        .subquery()
    )
    latest_snapshots = (
        db.query(
            ranked_snapshots.c.player_key,
            ranked_snapshots.c.nickname,
            ranked_snapshots.c.player_uuid,
            ranked_snapshots.c.source_payload,
            ranked_snapshots.c.elo,
            ranked_snapshots.c.captured_at,
        )
        .filter(ranked_snapshots.c.snapshot_number == 1)
        .subquery()
    )
    match_totals = (
        db.query(
            player_key.label("player_key"),
            func.count(func.distinct(MatchParticipant.match_id)).label("matches"),
            func.sum(
                case((MatchParticipant.is_winner.is_(True), 1), else_=0)
            ).label("wins"),
        )
        .join(Match, Match.id == MatchParticipant.match_id)
        .filter(
            Match.rating_patch_family == patch_family,
            MatchParticipant.is_observer.is_(False),
        )
        .group_by(player_key)
        .subquery()
    )

    rated_query = (
        db.query(
            latest_snapshots.c.nickname,
            latest_snapshots.c.player_uuid,
            latest_snapshots.c.source_payload,
            latest_snapshots.c.elo,
            latest_snapshots.c.captured_at,
            match_totals.c.matches,
            match_totals.c.wins,
        )
        .join(
            match_totals,
            match_totals.c.player_key == latest_snapshots.c.player_key,
        )
    )
    rated_rows = rated_query.all()
    account_rows = (
        db.query(User, ExternalPlayerIdentity, Clan)
        .outerjoin(
            ExternalPlayerIdentity,
            and_(
                ExternalPlayerIdentity.user_id == User.id,
                ExternalPlayerIdentity.source == "bfmeladder",
            ),
        )
        .outerjoin(ClanMember, ClanMember.user_id == User.id)
        .outerjoin(Clan, Clan.id == ClanMember.clan_id)
        .filter(User.is_active.is_(True), User.is_claimed.is_(True))
        .all()
    )
    accounts_by_key = {}
    accounts_by_uuid = {}
    accounts_by_id = {}
    accounts = []
    for account, identity, clan in account_rows:
        item = {
            "user_id": account.id,
            "username": identity.current_nickname if identity else (account.display_name or account.username),
            "clan_id": clan.id if clan else None,
            "clan_name": clan.name if clan else None,
            "identity_nickname": identity.current_nickname if identity else None,
            "player_uuid": identity.external_uuid if identity else None,
            "aliases": [],
        }
        accounts.append(item)
        accounts_by_id[account.id] = item
        if item['player_uuid']:
            accounts_by_uuid[item['player_uuid']] = item
        for value in (account.username, item["identity_nickname"]):
            if value:
                accounts_by_key[str(value).strip().casefold()] = item

    alias_rows = (
        db.query(ExternalPlayerAlias.nickname, ExternalPlayerIdentity.user_id)
        .join(
            ExternalPlayerIdentity,
            ExternalPlayerIdentity.id == ExternalPlayerAlias.identity_id,
        )
        .filter(ExternalPlayerIdentity.source == "bfmeladder")
        .all()
    )
    for nickname, user_id in alias_rows:
        account = accounts_by_id.get(int(user_id))
        if account and nickname:
            accounts_by_key[str(nickname).strip().casefold()] = account
            if nickname not in account["aliases"]:
                account["aliases"].append(nickname)

    merged_players = []
    rated_account_ids = set()
    merged_accounts = {}
    for row in rated_rows:
        matches = int(row.matches or 0)
        wins = int(row.wins or 0)
        verified = not is_unverified_rating(SimpleNamespace(source_payload=row.source_payload),
                                            row.player_uuid, row.nickname)
        rating = round(float(row.elo), 2) if verified else None
        account = (accounts_by_uuid.get(row.player_uuid) if row.player_uuid else
                   accounts_by_key.get(str(row.nickname).strip().casefold()))
        if account:
            rated_account_ids.add(account["user_id"])
            captured_sort = (
                as_utc(row.captured_at).timestamp()
                if row.captured_at is not None
                else float("-inf")
            )
            player = merged_accounts.get(account["user_id"])
            if player is None:
                player = {
                    "username": account["username"],
                    "player_uuid": account['player_uuid'],
                    "rating_nickname": row.nickname,
                    "rating_aliases": [row.nickname],
                    "elo": rating,
                    "rated": verified,
                    "patch": patch_family,
                    "matches": 0,
                    "wins": 0,
                    "losses": 0,
                    "win_rate": 0,
                    "clan_id": account["clan_id"],
                    "clan_name": account["clan_name"],
                    "captured_at": row.captured_at.isoformat() if row.captured_at else None,
                    "_captured_sort": captured_sort,
                }
                merged_accounts[account["user_id"]] = player
            elif row.nickname not in player["rating_aliases"]:
                player["rating_aliases"].append(row.nickname)
            if captured_sort > player["_captured_sort"]:
                player["rating_nickname"] = row.nickname
                player["elo"] = rating
                player['rated'] = verified
                player["captured_at"] = row.captured_at.isoformat() if row.captured_at else None
                player["_captured_sort"] = captured_sort
            player["matches"] += matches
            player["wins"] += wins
        else:
            merged_players.append({
                "username": row.nickname,
                "player_uuid": row.player_uuid,
                "rating_nickname": row.nickname,
                "rating_aliases": [row.nickname],
                "elo": rating,
                "rated": verified,
                "patch": patch_family,
                "matches": matches,
                "wins": wins,
                "losses": max(0, matches - wins),
                "win_rate": round(wins / matches * 100, 1) if matches else 0,
                "clan_id": None,
                "clan_name": None,
                "captured_at": row.captured_at.isoformat() if row.captured_at else None,
            })

    for player in merged_accounts.values():
        player.pop("_captured_sort", None)
        player["losses"] = max(0, player["matches"] - player["wins"])
        player["win_rate"] = (
            round(player["wins"] / player["matches"] * 100, 1)
            if player["matches"]
            else 0
        )
        player["rating_aliases"].sort(key=str.casefold)
        merged_players.append(player)

    for account in accounts:
        if account["user_id"] in rated_account_ids:
            continue
        merged_players.append({
            "username": account["username"],
            "player_uuid": account['player_uuid'],
            "rating_nickname": account["identity_nickname"],
            "rating_aliases": sorted(
                {
                    value
                    for value in (
                        account["identity_nickname"],
                        *account["aliases"],
                    )
                    if value
                },
                key=str.casefold,
            ),
            "elo": None,
            "rated": False,
            "patch": patch_family,
            "matches": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "clan_id": account["clan_id"],
            "clan_name": account["clan_name"],
            "captured_at": None,
        })

    if accounts_by_uuid:
        live_rows = await arena_current_ratings.fetch_patch(patch_family)
        live_by_uuid = {uuid: elo for _, uuid, elo in live_rows if uuid}
        for player in merged_players:
            live_elo = live_by_uuid.get(player.get('player_uuid'))
            if live_elo is not None:
                player['elo'] = live_elo
                player['rated'] = True

    search_key = (search or "").strip().casefold()
    if search_key:
        merged_players = [
            item for item in merged_players
            if any(
                search_key in str(value).casefold()
                for value in (
                    item["username"],
                    item["rating_nickname"],
                    *item["rating_aliases"],
                    item["clan_name"],
                )
                if value
            )
        ]
    if min_elo is not None:
        merged_players = [
            item for item in merged_players
            if item["elo"] is not None and item["elo"] >= min_elo
        ]
    if max_elo is not None:
        merged_players = [
            item for item in merged_players
            if item["elo"] is not None and item["elo"] <= max_elo
        ]

    if sort == "elo_asc":
        merged_players.sort(key=lambda item: (
            item["elo"] is None,
            item["elo"] if item["elo"] is not None else 0,
            item["username"].casefold(),
        ))
    elif sort == "matches_desc":
        merged_players.sort(key=lambda item: (
            -item["matches"],
            item["elo"] is None,
            -(item["elo"] or 0),
            item["username"].casefold(),
        ))
    else:
        merged_players.sort(key=lambda item: (
            item["elo"] is None,
            -(item["elo"] or 0),
            item["username"].casefold(),
        ))

    total_players = len(merged_players)
    page_start = (page - 1) * limit
    players = []
    for position, item in enumerate(
        merged_players[page_start:page_start + limit],
        start=page_start + 1,
    ):
        players.append({"position": position, **item})

    return {
        "players": players,
        "total_players": total_players,
        "current_page": page,
        "total_pages": max(1, (total_players + limit - 1) // limit),
        "patch": patch_family,
        "sort": sort,
    }

@router.get("/matches")
async def get_matches(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    faction: str = Query(None),
    player: str = Query(None),
    patch: str = Query(None),
    game_mode: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Получает список матчей с фильтрацией и пагинацией"""
    try:
        query = db.query(Match)
        
        # Применяем фильтры
        factions = [
            item.strip()
            for item in (faction or "").split(",")
            if item.strip()
        ]
        if factions:
            query = query.filter(
                or_(
                    Match.winner_faction.in_(factions),
                    Match.loser_faction.in_(factions),
                    Match.participants.any(MatchParticipant.faction.in_(factions)),
                )
            )
        
        if player:
            query = query.filter(
                or_(
                    Match.winner_player.ilike(f"%{player}%"),
                    Match.loser_player.ilike(f"%{player}%"),
                    Match.participants.any(MatchParticipant.nickname.ilike(f"%{player}%")),
                )
            )

        patch_key = (patch or "").strip().lower()
        if patch_key == "ennorath":
            query = query.filter(
                or_(
                    Match.rating_patch_family == "ennorath",
                    func.lower(Match.patch_name).like("%ennorath%"),
                    func.lower(Match.patch_version).like("%ennorath%"),
                )
            )
        elif patch_key == "patch_202":
            query = query.filter(
                or_(
                    Match.rating_patch_family == "patch_202",
                    func.lower(Match.patch_name).like("%2.02%"),
                    func.lower(Match.patch_version).like("%2.02%"),
                )
            )

        mode_key = (game_mode or "").strip().lower()
        mode_variants = {
            "1v1": ("1v1", "1 vs 1", "1 versus 1"),
            "2v2": ("2v2", "2 vs 2", "2 versus 2"),
            "3v3": ("3v3", "3 vs 3", "3 versus 3"),
            "4v4": ("4v4", "4 vs 4", "4 versus 4"),
        }
        if mode_key in mode_variants:
            variants = mode_variants[mode_key]
            query = query.filter(
                or_(
                    func.lower(Match.gamemode_name).in_(variants),
                    func.lower(Match.game_mode).in_(variants),
                )
            )
        
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, "%Y-%m-%d")
                query = query.filter(Match.match_date >= date_from_obj)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
                query = query.filter(Match.match_date < date_to_obj)
            except ValueError:
                pass
        
        # Считаем только идентификаторы, не загружая тяжёлые данные матчей.
        total_matches = (
            query.with_entities(func.count(Match.id)).scalar()
            or 0
        )
        total_pages = (total_matches + limit - 1) // limit
        
        # Для таблицы выбираем только те поля, которые реально показывает интерфейс.
        matches = query.with_entities(
            Match.id,
            Match.match_id,
            Match.winner_player,
            Match.winner_faction,
            Match.loser_player,
            Match.loser_faction,
            Match.match_date,
            Match.duration,
            Match.map_name,
            Match.game_mode,
            Match.gamemode_name,
            Match.patch_name,
            Match.patch_version,
            Match.rating_patch_family,
        ).order_by(Match.match_date.desc())\
            .offset((page - 1) * limit)\
            .limit(limit)\
            .all()

        match_ids = [match.id for match in matches]
        participant_rows = (
            db.query(MatchParticipant)
            .filter(MatchParticipant.match_id.in_(match_ids))
            .order_by(MatchParticipant.match_id, MatchParticipant.team, MatchParticipant.id)
            .all()
            if match_ids else []
        )
        participants_by_match = defaultdict(list)
        for participant in participant_rows:
            participants_by_match[participant.match_id].append({
                "id": participant.id,
                "username": participant.nickname,
                "player_uuid": participant.player_uuid,
                "faction": participant.faction,
                "team": participant.team,
                "is_winner": participant.is_winner,
                "is_observer": participant.is_observer,
                "elo": participant.elo,
                "old_rank": participant.old_rank,
                "new_rank": participant.new_rank,
            })
        
        # Преобразуем в словари
        matches_data = []
        for match in matches:
            participants = participants_by_match.get(match.id, [])
            if not participants:
                participants = [
                    {
                        "username": match.winner_player,
                        "faction": match.winner_faction,
                        "team": 1,
                        "is_winner": True,
                        "is_observer": False,
                    },
                    {
                        "username": match.loser_player,
                        "faction": match.loser_faction,
                        "team": 2,
                        "is_winner": False,
                        "is_observer": False,
                    },
                ]
            matches_data.append({
                "id": match.id,
                "match_id": match.match_id,
                "winner_player": match.winner_player,
                "winner_faction": match.winner_faction,
                "loser_player": match.loser_player,
                "loser_faction": match.loser_faction,
                "match_date": match.match_date.isoformat(),
                "duration": match.duration,
                "map_name": match.map_name,
                "game_mode": match.gamemode_name or match.game_mode,
                "gamemode_name": match.gamemode_name,
                "patch_name": match.patch_name,
                "patch_version": match.patch_version,
                "rating_patch_family": match.rating_patch_family,
                "participants": participants,
                "map_preview_url": map_preview_storage.public_url(match.map_name),
            })
        
        return {
            "matches": matches_data,
            "total_matches": total_matches,
            "total_pages": total_pages,
            "current_page": page,
            "limit": limit
        }
    except Exception as e:
        logger.error(f"Ошибка получения матчей: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения матчей") 


@router.get("/matches/{match_ref}/replay")
async def download_match_replay(
    match_ref: str,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Скачать replay из локального архива, при необходимости сохранив его с Arena."""
    match = _match_by_reference(db, match_ref)
    storage = ReplayStorageService()
    if not storage.is_supported(match):
        raise HTTPException(
            status_code=422,
            detail="Replay доступен только для Ennorath и Patch 2.02",
        )

    replay_path = Path(match.replay_local_path).resolve() if match.replay_local_path else storage.target_path(match).resolve()
    if not replay_path.is_file():
        timeout = aiohttp.ClientTimeout(total=120, connect=20)
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            saved = await storage.download_match(db, match, session)
        if not saved:
            raise HTTPException(
                status_code=502,
                detail=match.replay_download_error or "Не удалось получить replay с Arena",
            )
        replay_path = Path(match.replay_local_path).resolve()

    storage_root = Path(settings.REPLAY_STORAGE_DIR).resolve()
    try:
        replay_path.relative_to(storage_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Недопустимый путь replay") from exc

    if not replay_path.is_file():
        raise HTTPException(status_code=404, detail="Replay отсутствует в архиве")
    return FileResponse(
        replay_path,
        media_type="application/octet-stream",
        filename=storage.target_path(match).name,
    )


@router.get("/matches/{match_ref}")
def get_match_detail(
    match_ref: str,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Полные безопасные данные одного матча для общего окна деталей."""
    return _match_detail_payload(_match_by_reference(db, match_ref))


@router.get("/map-previews/{map_key}", include_in_schema=False)
def get_map_preview(map_key: str):
    preview_path = map_preview_storage.resolve_key(map_key)
    if preview_path is None:
        raise HTTPException(status_code=404, detail="Превью карты не найдено")
    with preview_path.open("rb") as preview_file:
        media_type = map_preview_storage.media_type(preview_file.read(16))
    if media_type is None:
        raise HTTPException(status_code=415, detail="Формат превью карты не поддерживается")
    return FileResponse(
        preview_path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=2592000, immutable"},
    )


@router.get("/live")
async def get_live_matches(
    player: str = Query(None),
    current_user: UserModel = Depends(get_current_active_user),
):
    """Return live matches from a shared ten-minute cache."""
    if time.monotonic() >= _live_cache["expires_at"]:
        async with _live_cache_lock:
            if time.monotonic() >= _live_cache["expires_at"]:
                _live_cache["matches"] = await ladder_service.get_live_matches()
                _live_cache["updated_at"] = datetime.now().isoformat()
                _live_cache["expires_at"] = time.monotonic() + LIVE_CACHE_TTL

    matches = _live_cache["matches"]
    if player:
        needle = player.casefold()
        matches = [
            match for match in matches
            if needle in str(match.get("player1", "")).casefold()
            or needle in str(match.get("player2", "")).casefold()
        ]
    return {
        "matches": matches,
        "updated_at": _live_cache["updated_at"],
        "refresh_seconds": LIVE_CACHE_TTL,
    }
