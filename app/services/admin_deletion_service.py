from fastapi import HTTPException
from sqlalchemy import delete, select, update, or_

from app.database import Base
from app.models.clan import Clan
from app.models.war import ClanWar
from app.models.territory import Territory
from app.models.campaign import CampaignSeasonClanResult
from app.models.notification import UserNotification
from app.models.operation import AdminAuditLog
from app.services.war_service import ClanWarService
from app.services.market_service import ClanMarketService


def _delete_dependents(db, table, condition):
    """Detach optional history and recursively remove required owned records."""
    for child in Base.metadata.sorted_tables:
        for fk in child.foreign_keys:
            if fk.column.table is not table:
                continue
            column = fk.parent
            linked = column.in_(select(fk.column).where(condition))
            owned = table.name == "clans" and child.name in {
                "clan_members", "clan_invites", "clan_applications",
            }
            if column.nullable and not owned:
                db.execute(update(child).where(linked).values({column.name: None}))
            else:
                _delete_dependents(db, child, linked)
    db.execute(delete(table).where(condition))


def _remove_notices(db, entity_type, entity_id):
    db.execute(delete(UserNotification).where(
        UserNotification.entity_type == entity_type,
        UserNotification.entity_id == entity_id,
    ))
    db.execute(delete(AdminAuditLog).where(
        AdminAuditLog.entity_type == entity_type,
        AdminAuditLog.entity_id == str(entity_id),
    ))


class AdminDeletionService:
    def delete_war(self, db, war_id):
        war = db.query(ClanWar).filter(ClanWar.id == war_id).with_for_update().first()
        if war is None:
            raise HTTPException(404, "Битва не найдена")
        if war.status == "active":
            ClanWarService().cancel_war(db, war.id, refund_attack=True, commit=False)
        db.flush()
        _remove_notices(db, "clan_war", war_id)
        _remove_notices(db, "war", war_id)
        _delete_dependents(db, ClanWar.__table__, ClanWar.__table__.c.id == war_id)
        db.expire_all()

    def delete_clan(self, db, clan_id):
        market = ClanMarketService()
        market.lock_market(db)
        clan = db.query(Clan).filter(Clan.id == clan_id).with_for_update().first()
        if clan is None:
            raise HTTPException(404, "Клан не найден")
        if clan.is_admin_clan:
            raise HTTPException(409, "Системный клан нельзя удалить")
        market.cancel_for_clan(db, clan_id)
        service = ClanWarService()
        wars = db.query(ClanWar).filter(or_(
            ClanWar.attacking_clan_id == clan_id,
            ClanWar.defending_clan_id == clan_id,
        )).with_for_update().all()
        for war in wars:
            if war.status == "active":
                service.cancel_war(db, war.id, refund_attack=True, commit=False)
            _remove_notices(db, "war", war.id)
            _remove_notices(db, "clan_war", war.id)
            snapshot = dict(war.rules_snapshot or {})
            if "RELIC_BONUSES_BY_CLAN" in snapshot:
                snapshot["RELIC_BONUSES_BY_CLAN"] = {
                    key: value for key, value in snapshot["RELIC_BONUSES_BY_CLAN"].items()
                    if key != str(clan_id)
                }
                war.rules_snapshot = snapshot
        db.flush()
        db.execute(update(Territory).where(Territory.owner_clan_id == clan_id).values(
            owner_clan_id=None, status="neutral",
        ))
        db.execute(update(CampaignSeasonClanResult).where(
            CampaignSeasonClanResult.clan_id == clan_id,
        ).values(clan_name="Удалённый клан", clan_avatar_url=None, clan_map_color=None))
        _remove_notices(db, "clan", clan_id)
        _delete_dependents(db, Clan.__table__, Clan.__table__.c.id == clan_id)
        db.expire_all()
