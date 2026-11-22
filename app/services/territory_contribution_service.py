from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.campaign import CampaignSeason
from app.models.user import User
from app.models.war import ClanWar, ClanWarMatchResult


class TerritoryContributionService:
    def calculate(
        self,
        db: Session,
        *,
        user: User,
        season_id: int | None = None,
    ) -> dict:
        season = None
        if season_id is not None:
            season = db.query(CampaignSeason).filter(
                CampaignSeason.id == season_id
            ).first()
            if season is None:
                raise HTTPException(status_code=404, detail="Сезон не найден")
        else:
            season = db.query(CampaignSeason).filter(
                CampaignSeason.status == "active"
            ).first()

        query = (
            db.query(ClanWarMatchResult)
            .options(
                joinedload(ClanWarMatchResult.war).joinedload(ClanWar.territory),
                joinedload(ClanWarMatchResult.winner_clan),
                joinedload(ClanWarMatchResult.loser_clan),
            )
            .filter(
                ClanWarMatchResult.is_counted.is_(True),
                or_(
                    ClanWarMatchResult.winner_user_id == user.id,
                    ClanWarMatchResult.loser_user_id == user.id,
                ),
            )
        )
        if season is not None:
            query = query.filter(ClanWarMatchResult.played_at >= season.starts_at)
            if season.ends_at is not None:
                query = query.filter(ClanWarMatchResult.played_at <= season.ends_at)

        rows = query.order_by(ClanWarMatchResult.played_at.desc()).all()
        territories = defaultdict(lambda: {
            "war_ids": set(),
            "matches": 0,
            "wins": 0,
            "losses": 0,
            "score": 0.0,
            "last_action_at": None,
            "clan_id": None,
            "clan_name": None,
        })
        war_ids = set()
        total_wins = 0
        total_score = 0.0

        for row in rows:
            is_winner = row.winner_user_id == user.id
            points = float(
                row.winner_total_points if is_winner else row.loser_total_points
            )
            clan = row.winner_clan if is_winner else row.loser_clan
            territory = row.war.territory if row.war else None
            if territory is None:
                continue

            entry = territories[territory.id]
            entry["territory_id"] = territory.id
            entry["territory_name"] = territory.name
            entry["war_ids"].add(row.war_id)
            entry["matches"] += 1
            entry["wins"] += 1 if is_winner else 0
            entry["losses"] += 0 if is_winner else 1
            entry["score"] += points
            if entry["last_action_at"] is None or row.played_at > entry["last_action_at"]:
                entry["last_action_at"] = row.played_at
                entry["clan_id"] = clan.id if clan else None
                entry["clan_name"] = clan.name if clan else None

            war_ids.add(row.war_id)
            total_wins += 1 if is_winner else 0
            total_score += points

        serialized = []
        for entry in territories.values():
            serialized.append({
                **{key: value for key, value in entry.items() if key != "war_ids"},
                "wars": len(entry["war_ids"]),
                "score": round(entry["score"], 2),
            })
        serialized.sort(key=lambda item: (-item["score"], item["territory_name"]))

        return {
            "season_id": season.id if season else None,
            "season_name": season.name if season else None,
            "summary": {
                "wars": len(war_ids),
                "matches": len(rows),
                "wins": total_wins,
                "losses": max(0, len(rows) - total_wins),
                "score": round(total_score, 2),
                "territories_helped": len(serialized),
            },
            "territories": serialized,
        }
