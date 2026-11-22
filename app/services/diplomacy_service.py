from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.permissions import ClanPermission, require_clan_permission
from app.core.campaign_mode import INTERSEASON_MESSAGE, is_interseason, cycle_owns_campaign
from app.models.clan import Clan
from app.models.diplomacy import ClanDiplomacyEvent, ClanDiplomaticRelation
from app.models.user import User
from app.services.notification_service import notification_service


class ClanDiplomacyService:
    ACTIVE_STATUSES = {"pending_alliance", "allied", "hostile"}

    @staticmethod
    def _pair(first_clan_id: int, second_clan_id: int) -> tuple[int, int]:
        if first_clan_id == second_clan_id:
            raise HTTPException(status_code=400, detail="Нельзя установить отношения с собственным кланом")
        return tuple(sorted((int(first_clan_id), int(second_clan_id))))

    def _query(self, db: Session):
        return db.query(ClanDiplomaticRelation).options(
            joinedload(ClanDiplomaticRelation.clan_low),
            joinedload(ClanDiplomaticRelation.clan_high),
            joinedload(ClanDiplomaticRelation.events).joinedload(ClanDiplomacyEvent.actor_clan),
        )

    @staticmethod
    def serialize(
        relation: ClanDiplomaticRelation,
        *,
        include_events: bool = True,
    ) -> dict:
        def clan_summary(clan: Clan) -> dict:
            return {
                "id": clan.id,
                "name": clan.name,
                "avatar_url": clan.avatar_url,
                "map_color": clan.map_color,
            }

        return {
            "id": relation.id,
            "clan_low": clan_summary(relation.clan_low),
            "clan_high": clan_summary(relation.clan_high),
            "status": relation.status,
            "requested_by_clan_id": relation.requested_by_clan_id,
            "updated_at": relation.updated_at,
            "events": [
                {
                    "id": event.id,
                    "actor_clan_id": event.actor_clan_id,
                    "actor_clan_name": event.actor_clan.name if event.actor_clan else None,
                    "previous_status": event.previous_status,
                    "new_status": event.new_status,
                    "note": event.note,
                    "created_at": event.created_at,
                }
                for event in relation.events[:20]
            ] if include_events else [],
        }

    def list_relations(
        self,
        db: Session,
        *,
        clan_id: int | None = None,
        include_neutral: bool = False,
    ) -> list[dict]:
        if is_interseason(db) or cycle_owns_campaign(db):
            return []
        query = self._query(db)
        if clan_id is not None:
            query = query.filter(
                (ClanDiplomaticRelation.clan_low_id == clan_id)
                | (ClanDiplomaticRelation.clan_high_id == clan_id)
            )
        if not include_neutral:
            query = query.filter(ClanDiplomaticRelation.status.in_(self.ACTIVE_STATUSES))
        relations = query.order_by(
            ClanDiplomaticRelation.updated_at.desc(),
            ClanDiplomaticRelation.id.desc(),
        ).all()
        # The catalogue needs the diplomatic status, not private negotiation
        # notes.  Detailed audit events stay server-side and are only returned
        # to a manager as the result of their own action.
        return [self.serialize(relation, include_events=False) for relation in relations]

    def act(
        self,
        db: Session,
        *,
        actor_clan_id: int,
        other_clan_id: int,
        actor: User,
        action: str,
        note: str | None = None,
    ) -> dict:
        if is_interseason(db):
            raise HTTPException(status_code=409, detail=INTERSEASON_MESSAGE)
        if cycle_owns_campaign(db):
            raise HTTPException(status_code=409, detail='Для нового сезона используйте страницу дипломатии текущего цикла.')
        actor_clan, _ = require_clan_permission(
            db,
            actor_clan_id,
            actor,
            ClanPermission.MANAGE_CLAN,
        )
        other_clan = db.query(Clan).filter(Clan.id == other_clan_id).first()
        if other_clan is None or other_clan.is_deleted:
            raise HTTPException(status_code=404, detail="Клан не найден")
        if actor_clan.is_admin_clan or other_clan.is_admin_clan:
            raise HTTPException(status_code=400, detail="Системные кланы не участвуют в дипломатии")

        low_id, high_id = self._pair(actor_clan_id, other_clan_id)
        relation = self._query(db).filter(
            ClanDiplomaticRelation.clan_low_id == low_id,
            ClanDiplomaticRelation.clan_high_id == high_id,
        ).first()
        if relation is None:
            relation = ClanDiplomaticRelation(
                clan_low_id=low_id,
                clan_high_id=high_id,
                status="neutral",
            )
            db.add(relation)
            db.flush()

        previous_status = relation.status
        if action == "propose_alliance":
            if relation.status == "allied":
                raise HTTPException(status_code=409, detail="Кланы уже состоят в союзе")
            if relation.status == "pending_alliance" and relation.requested_by_clan_id != actor_clan_id:
                raise HTTPException(status_code=409, detail="Другой клан уже предложил союз — примите или отклоните его")
            if relation.status == "pending_alliance" and relation.requested_by_clan_id == actor_clan_id:
                return self.serialize(relation)
            relation.status = "pending_alliance"
            relation.requested_by_clan_id = actor_clan_id
        elif action == "accept_alliance":
            if relation.status != "pending_alliance" or relation.requested_by_clan_id == actor_clan_id:
                raise HTTPException(status_code=409, detail="Нет входящего предложения союза")
            relation.status = "allied"
            relation.requested_by_clan_id = None
        elif action == "reject_alliance":
            if relation.status != "pending_alliance" or relation.requested_by_clan_id == actor_clan_id:
                raise HTTPException(status_code=409, detail="Нет входящего предложения союза")
            relation.status = "neutral"
            relation.requested_by_clan_id = None
        elif action == "declare_hostility":
            if relation.status == "hostile" and relation.requested_by_clan_id == actor_clan_id:
                return self.serialize(relation)
            relation.status = "hostile"
            relation.requested_by_clan_id = actor_clan_id
        elif action == "set_neutral":
            if relation.status == "neutral":
                return self.serialize(relation)
            relation.status = "neutral"
            relation.requested_by_clan_id = None
        else:
            raise HTTPException(status_code=422, detail="Неизвестное дипломатическое действие")

        relation.updated_by_user_id = actor.id
        db.add(ClanDiplomacyEvent(
            relation_id=relation.id,
            actor_clan_id=actor_clan_id,
            actor_user_id=actor.id,
            previous_status=previous_status,
            new_status=relation.status,
            note=(note or "").strip() or None,
        ))
        notification_service.create_for_clan(
            db,
            clan_id=other_clan_id,
            notification_type="diplomacy",
            title="Изменение дипломатических отношений",
            message=f"Клан «{actor_clan.name}» изменил статус отношений: {relation.status}.",
            link_url="/clans",
            entity_type="clan_diplomacy",
            entity_id=relation.id,
            excluded_user_id=actor.id,
            commit=False,
        )
        db.commit()
        relation = self._query(db).filter(ClanDiplomaticRelation.id == relation.id).first()
        return self.serialize(relation)


diplomacy_service = ClanDiplomacyService()
