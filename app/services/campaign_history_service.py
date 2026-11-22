from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.campaign_rules import RULE_DEFINITIONS
from app.core.time import as_utc, utc_now
from app.models.campaign import CampaignRuleSet, CampaignSeason, CampaignSeasonClanResult
from app.models.clan import Clan
from app.models.operation import ResourceLedgerEntry
from app.models.territory import Territory
from app.models.war import ClanWar
from app.services.campaign_rule_service import CampaignRuleService


INFLUENCE_ACTION_LABELS = {
    "territory_influence_gained": "Получено влияние территории",
    "territory_influence_lost": "Утрачено влияние территории",
    "territory_influence_recalculated": "Пересчитано влияние владений",
    "relic_influence_recalculated": "Применён бонус реликвии",
    "season_started": "Стартовое влияние сезона",
    "admin_resource_change": "Изменение администратором",
}


class CampaignHistoryService:
    """Фиксирует сезоны и формирует публичную историю влияния."""

    @classmethod
    def rules_snapshot(cls, db: Session) -> dict:
        snapshot = CampaignRuleService().get_active(db)
        return {
            "rule_set_id": snapshot.id,
            "version": snapshot.version,
            "values": dict(snapshot.values),
        }

    def get_active_season(self, db: Session) -> CampaignSeason | None:
        return (
            db.query(CampaignSeason)
            .filter(CampaignSeason.status == "active")
            .first()
        )

    def create_season(
        self,
        db: Session,
        *,
        starting_influence: int,
        reset_development: bool,
        actor_user_id: int | None,
        name: str | None = None,
        starts_at=None,
    ) -> CampaignSeason:
        number = (db.query(func.max(CampaignSeason.number)).scalar() or 0) + 1
        season = CampaignSeason(
            number=number,
            name=(name or f"Сезон {number}").strip()[:120],
            status="active",
            starting_influence=starting_influence,
            reset_development=reset_development,
            starts_at=starts_at or utc_now(),
            created_by_user_id=actor_user_id,
            rules_snapshot=self.rules_snapshot(db),
        )
        db.add(season)
        db.flush()
        return season

    def complete_active_season(self, db: Session, *, completed_at=None) -> CampaignSeason | None:
        db.flush()
        candidate = (db.query(CampaignSeason.id, CampaignSeason.rules_snapshot)
                     .filter_by(status="active").first())
        if candidate is None:
            return None
        cycle = None
        if (candidate.rules_snapshot or {}).get('mechanics_version') == 'cycle_v1':
            from app.models.campaign_cycle import CampaignCycleRecord

            # Match runtime/store ordering; never wait for a cycle while holding its season.
            cycle = (db.query(CampaignCycleRecord).filter_by(season_id=candidate.id)
                     .order_by(CampaignCycleRecord.number.desc()).with_for_update()
                     .populate_existing().first())
        season = (db.query(CampaignSeason).filter_by(id=candidate.id, status="active")
                  .populate_existing().with_for_update().first())
        if not season:
            return None
        if db.query(ClanWar.id).filter(ClanWar.status == "active").first() is not None:
            raise ValueError("Active legacy wars must be resolved before completing the season")
        completed_at = completed_at or utc_now()
        if (season.rules_snapshot or {}).get('mechanics_version') == 'cycle_v1':
            from app.services.campaign_cycle_store import CampaignCycleStore
            from app.services.campaign_cycle_service import CyclePhase

            if cycle is None or CampaignCycleStore.timeline(cycle).phase_at(as_utc(completed_at)) != CyclePhase.SEASON_ENDED:
                raise ValueError('Final cycle must be calculated after a manual season-end request')
        rankings = self._build_rankings(db, season.starts_at, completed_at)
        if (season.rules_snapshot or {}).get('mechanics_version') == 'cycle_v1':
            rankings = self._cycle_rankings(db, season, cycle, rankings)
        for row in rankings:
            db.add(
                CampaignSeasonClanResult(
                    season_id=season.id,
                    captured_at=completed_at,
                    **row,
                )
            )
        season.status = "completed"
        season.ends_at = completed_at
        db.flush()
        from app.services.season_archive_service import SeasonArchiveService

        SeasonArchiveService().capture(db, season)
        return season

    def _cycle_rankings(self, db, season, cycle, rows):
        from app.models.cycle_battle import CycleTerritoryBattle
        from app.models.cycle_economy import CycleEconomyState, CycleEconomySnapshot

        active = {clan.id for clan in db.query(Clan).filter(Clan.is_deleted.is_(False), Clan.is_admin_clan.is_(False))}
        rows = [row for row in rows if row['clan_id'] in active]
        land_influence = dict(db.query(Territory.owner_clan_id, func.sum(Territory.influence_value))
                              .group_by(Territory.owner_clan_id).all())
        states = {state.clan_id: state for state in db.query(CycleEconomyState).filter_by(season_id=season.id)}
        snapshots = {snap.state_id: snap for snap in db.query(CycleEconomySnapshot).filter_by(cycle_id=cycle.id)}
        totals = defaultdict(lambda: dict(wars_won=0, wars_lost=0, defenses_won=0))
        from app.models.campaign_cycle import CampaignCycleRecord
        battles = db.query(CycleTerritoryBattle).join(CampaignCycleRecord).filter(
            CampaignCycleRecord.season_id == season.id, CycleTerritoryBattle.completed_at.isnot(None))
        for battle in battles:
            winner = battle.winner_clan_id
            if winner is not None:
                totals[winner]['wars_won'] += 1
                totals[winner]['defenses_won'] += int(winner == battle.owner_clan_id)
            for side in battle.sides:
                if winner is not None and side['clan_id'] != winner:
                    totals[side['clan_id']]['wars_lost'] += 1
        for row in rows:
            state = states.get(row['clan_id'])
            snapshot = snapshots.get(state.id) if state else None
            bonus = sum((Decimal(effect['percent']) for effect in snapshot.effects if effect['effect'] == 'influence'), Decimal(0)) if snapshot else Decimal(0)
            # Keep the existing integer influence convention, excluding base influence.
            row['influence'] = int(Decimal(land_influence.get(row['clan_id']) or 0) * (1 + bonus / 100))
            row.update(totals[row['clan_id']])
            if state:
                for resource, amount in state.wallet.items():
                    row[resource] = int(Decimal(amount))
        rows.sort(key=lambda row: (-row['influence'], row['clan_id']))
        previous_score, rank = None, 0
        for position, row in enumerate(rows, 1):
            if row['influence'] != previous_score:
                rank = position
            row['rank'] = rank
            previous_score = row['influence']
        return rows

    def _build_rankings(self, db: Session, starts_at, ends_at) -> list[dict]:
        clans = (
            db.query(Clan)
            .filter(Clan.is_admin_clan.is_(False), Clan.is_deleted.is_(False))
            .all()
        )
        territory_counts = dict(
            db.query(Territory.owner_clan_id, func.count(Territory.id))
            .filter(Territory.owner_clan_id.isnot(None))
            .group_by(Territory.owner_clan_id)
            .all()
        )
        war_totals = defaultdict(lambda: {"wars_won": 0, "wars_lost": 0, "defenses_won": 0})
        wars = (
            db.query(ClanWar)
            .filter(
                ClanWar.status == "completed",
                ClanWar.ended_at.isnot(None),
                ClanWar.ended_at >= starts_at,
                ClanWar.ended_at <= ends_at,
            )
            .all()
        )
        for war in wars:
            if not war.winner_clan_id:
                continue
            war_totals[war.winner_clan_id]["wars_won"] += 1
            if war.defending_clan_id == war.winner_clan_id:
                war_totals[war.winner_clan_id]["defenses_won"] += 1
            for clan_id in (war.attacking_clan_id, war.defending_clan_id):
                if clan_id and clan_id != war.winner_clan_id:
                    war_totals[clan_id]["wars_lost"] += 1

        rows = []
        for clan in clans:
            totals = war_totals[clan.id]
            rows.append({
                "clan_id": clan.id,
                "clan_name": clan.name,
                "clan_avatar_url": clan.avatar_url,
                "clan_map_color": clan.map_color,
                "rank": 0,
                "influence": int(clan.territory_points or 0),
                "base_influence": int(clan.base_influence or 0),
                "territory_count": int(territory_counts.get(clan.id, 0)),
                "wars_won": totals["wars_won"],
                "wars_lost": totals["wars_lost"],
                "defenses_won": totals["defenses_won"],
                "gold": int(clan.gold or 0),
                "iron": int(clan.iron or 0),
                "wood": int(clan.wood or 0),
                "food": int(clan.food or 0),
                "mithril": int(clan.mithril or 0),
            })
        rows.sort(
            key=lambda row: (
                row["influence"],
                row["territory_count"],
                row["wars_won"],
                row["defenses_won"],
                row["clan_name"],
            ),
            reverse=True,
        )
        for rank, row in enumerate(rows, 1):
            row["rank"] = rank
        return rows

    def list_seasons(self, db: Session) -> list[dict]:
        seasons = db.query(CampaignSeason).order_by(CampaignSeason.number.desc()).all()
        return [self.season_summary(db, season) for season in seasons]

    def season_summary(self, db: Session, season: CampaignSeason) -> dict:
        result_count = (
            db.query(func.count(CampaignSeasonClanResult.id))
            .filter(CampaignSeasonClanResult.season_id == season.id)
            .scalar()
            or 0
        )
        leader = (
            db.query(CampaignSeasonClanResult)
            .filter(CampaignSeasonClanResult.season_id == season.id)
            .order_by(CampaignSeasonClanResult.rank.asc())
            .first()
        )
        return {
            "id": season.id,
            "number": season.number,
            "name": season.name,
            "status": season.status,
            "starting_influence": season.starting_influence,
            "starts_at": season.starts_at,
            "ends_at": season.ends_at,
            "rule_version": (season.rules_snapshot or {}).get("version"),
            "clan_count": result_count,
            "winner": self._serialize_result(leader) if leader else None,
        }

    def public_rules_snapshot(
        self,
        db: Session,
        *,
        season_id: int | None = None,
    ) -> dict | None:
        if season_id is not None:
            season = db.query(CampaignSeason).filter_by(id=season_id).one_or_none()
            if season is None:
                return None
        else:
            season = self.get_active_season(db)

        stored_rules = (
            season.rules_snapshot
            if season_id is not None and season is not None
            else None
        )
        if stored_rules and stored_rules.get("values"):
            stored_values = dict(stored_rules["values"])
            if set(stored_values) != set(RULE_DEFINITIONS):
                archived_row = (
                    db.query(CampaignRuleSet)
                    .filter_by(version=stored_rules.get("version"))
                    .one_or_none()
                )
                if archived_row is not None:
                    stored_values = dict(archived_row.values)
            rule_set = {
                "id": stored_rules.get("rule_set_id"),
                "version": stored_rules.get("version"),
                "values": stored_values,
                "complete": set(stored_values) == set(RULE_DEFINITIONS),
            }
        else:
            active = CampaignRuleService().get_active(db, create=False)
            rule_set = {
                "id": active.id,
                "version": active.version,
                "values": dict(active.values),
                "complete": True,
            }

        return {
            "rule_set": rule_set,
            "season": self.season_summary(db, season) if season is not None else None,
            "mechanics_version": (
                "cycle_v1"
                if season is not None
                and (season.rules_snapshot or {}).get("mechanics_version") == "cycle_v1"
                else None
            ),
        }

    def season_detail(self, db: Session, season_id: int) -> dict | None:
        season = db.query(CampaignSeason).filter(CampaignSeason.id == season_id).first()
        if not season:
            return None
        if season.status == "active":
            rankings = self._build_rankings(db, season.starts_at, utc_now())
        else:
            rankings = [self._serialize_result(item) for item in season.results]
        return {
            **self.season_summary(db, season),
            "rules": season.rules_snapshot or {},
            "rankings": rankings,
        }

    def influence_history(
        self,
        db: Session,
        *,
        clan_id: int | None = None,
        season_id: int | None = None,
        limit: int = 200,
    ) -> dict:
        clans = (
            db.query(Clan)
            .filter(Clan.is_admin_clan.is_(False))
            .order_by(Clan.territory_points.desc(), Clan.name.asc())
            .all()
        )
        query = (
            db.query(ResourceLedgerEntry, Clan)
            .join(Clan, Clan.id == ResourceLedgerEntry.clan_id)
            .filter(
                ResourceLedgerEntry.resource == "influence",
                Clan.is_admin_clan.is_(False),
            )
        )
        season = None
        if season_id:
            season = db.query(CampaignSeason).filter(CampaignSeason.id == season_id).first()
            if season:
                query = query.filter(ResourceLedgerEntry.created_at >= season.starts_at)
                if season.ends_at:
                    query = query.filter(ResourceLedgerEntry.created_at <= season.ends_at)
        if clan_id:
            query = query.filter(ResourceLedgerEntry.clan_id == clan_id)
        rows = query.order_by(ResourceLedgerEntry.created_at.desc(), ResourceLedgerEntry.id.desc()).limit(limit).all()
        events = []
        for entry, clan in rows:
            details = entry.details or {}
            events.append({
                "id": entry.id,
                "clan_id": clan.id,
                "clan_name": clan.name,
                "clan_avatar_url": clan.avatar_url,
                "clan_map_color": clan.map_color,
                "amount": entry.amount,
                "balance_before": entry.balance_before,
                "balance_after": entry.balance_after,
                "action": entry.action,
                "action_label": INFLUENCE_ACTION_LABELS.get(entry.action, "Изменение влияния"),
                "territory_name": details.get("territory_name"),
                "reason": details.get("reason"),
                "created_at": entry.created_at,
            })
        return {
            "active_season": self.season_summary(db, self.get_active_season(db)) if self.get_active_season(db) else None,
            "selected_season": self.season_summary(db, season) if season else None,
            "clans": [
                {
                    "id": clan.id,
                    "name": clan.name,
                    "avatar_url": clan.avatar_url,
                    "map_color": clan.map_color,
                    "influence": int(clan.territory_points or 0),
                    "base_influence": int(clan.base_influence or 0),
                    "territory_influence": max(0, int(clan.territory_points or 0) - int(clan.base_influence or 0)),
                }
                for clan in clans
            ],
            "events": events,
        }

    @staticmethod
    def _serialize_result(result: CampaignSeasonClanResult | None) -> dict | None:
        if not result:
            return None
        return {
            "clan_id": result.clan_id,
            "clan_name": result.clan_name,
            "clan_avatar_url": result.clan_avatar_url,
            "clan_map_color": result.clan_map_color,
            "rank": result.rank,
            "influence": result.influence,
            "base_influence": result.base_influence,
            "territory_count": result.territory_count,
            "wars_won": result.wars_won,
            "wars_lost": result.wars_lost,
            "defenses_won": result.defenses_won,
            "gold": result.gold,
            "iron": result.iron,
            "wood": result.wood,
            "food": result.food,
            "mithril": result.mithril,
            "captured_at": result.captured_at,
        }
