from sqlalchemy.orm import Session

from app.models.clan import Clan
from app.models.clan_asset import ClanOwnedAsset
from app.models.operation import ResourceLedgerEntry
from app.models.territory import Territory
from app.core.economy_balance import is_admin_territory_name


class ClanInfluenceService:
    def get_territory_bonus_percent(self, db: Session, clan_id: int) -> int:
        owned_assets = (
            db.query(ClanOwnedAsset)
            .filter(ClanOwnedAsset.clan_id == clan_id)
            .all()
        )
        return sum(
            (item.asset.bonus_value or 0) * (item.level or 1)
            for item in owned_assets
            if item.asset and item.asset.bonus_type == "territory_points_percent"
        )

    def get_territory_influence(
        self,
        db: Session,
        territory: Territory,
        clan_id: int | None = None,
    ) -> int:
        clan_id = clan_id or territory.owner_clan_id
        bonus_percent = (
            self.get_territory_bonus_percent(db, clan_id)
            if clan_id else 0
        )
        return int(
            (territory.influence_value or 0)
            * (100 + bonus_percent)
            / 100
        )

    def recalculate(
        self,
        db: Session,
        clan_id: int | None,
        *,
        operation_id: str | None = None,
        action: str = "territory_influence_recalculated",
        source_type: str | None = None,
        source_id: str | int | None = None,
        actor_user_id: int | None = None,
        details: dict | None = None,
    ) -> int:
        if not clan_id:
            return 0
        clan = db.query(Clan).filter(Clan.id == clan_id).first()
        if not clan:
            return 0

        territory_value = sum(
            territory.influence_value or 0
            for territory in db.query(Territory)
            .filter(Territory.owner_clan_id == clan_id)
            .all()
            if not is_admin_territory_name(territory.name)
        )
        bonus_percent = self.get_territory_bonus_percent(db, clan_id)
        territory_bonus = int(territory_value * (100 + bonus_percent) / 100)
        before = int(clan.territory_points or 0)
        after = max(0, int(clan.base_influence or 0) + territory_bonus)
        clan.territory_points = after

        if operation_id and before != after:
            db.add(
                ResourceLedgerEntry(
                    operation_id=operation_id,
                    clan_id=clan.id,
                    resource="influence",
                    amount=after - before,
                    balance_before=before,
                    balance_after=after,
                    action=action,
                    source_type=source_type,
                    source_id=str(source_id) if source_id is not None else None,
                    actor_user_id=actor_user_id,
                    details={
                        "base_influence": int(clan.base_influence or 0),
                        "territory_influence": territory_bonus,
                        "territory_bonus_percent": bonus_percent,
                        **(details or {}),
                    },
                )
            )
        return after
