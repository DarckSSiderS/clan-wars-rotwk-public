from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user
from app.database import get_db
from app.models.clan_warfare import ClanLevelEvent
from app.models.operation import AdminAuditLog
from app.models.user import User
from app.services.war_service import ClanWarService


router = APIRouter(
    prefix="/admin/clan-warfare",
    tags=["admin-clan-warfare"],
)


@router.get("/wars/{war_id:int}")
def get_admin_clan_warfare_war(
    war_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
):
    service = ClanWarService()
    war = service.get_war(db, war_id)
    payload = service.serialize_war(db, war)
    payload["admin_warfare"] = {
        "campaign_rule_set_id": war.campaign_rule_set_id,
        "rules_snapshot": dict(war.rules_snapshot or {}),
        "deployments": [
            {
                "id": deployment.id,
                "clan_id": deployment.clan_id,
                "claim_sequence": deployment.claim_sequence,
                "source_territory_id": deployment.source_territory_id,
                "territory_count_snapshot": deployment.territory_count_snapshot,
                "defense_rule": deployment.defense_rule,
                "initial_role": deployment.initial_role,
                "current_role": deployment.current_role,
                "eligibility_scope": deployment.eligibility_scope,
                "assigned_by_user_id": deployment.assigned_by_user_id,
                "assigned_by_username": (
                    deployment.assigned_by_user.username
                    if deployment.assigned_by_user else None
                ),
                "assigned_at": deployment.assigned_at,
                "campaign_rule_set_id": deployment.campaign_rule_set_id,
                "rule_version": deployment.rule_version,
                "attack_lock_released_at": deployment.attack_lock_released_at,
                "role_changed_at": deployment.role_changed_at,
                "members": [
                    {
                        "user_id": member.user_id,
                        "username_snapshot": member.username_snapshot,
                        "nickname_snapshot": member.nickname_snapshot,
                        "external_uuid_snapshot": member.external_uuid_snapshot,
                        "avatar_url_snapshot": member.avatar_url_snapshot,
                        "membership_started_at": member.membership_started_at,
                        "assigned_at": member.assigned_at,
                        "released_at": member.released_at,
                    }
                    for member in deployment.members
                ],
            }
            for deployment in sorted(
                war.deployments,
                key=lambda item: item.claim_sequence,
            )
        ],
        "attack_point_spends": [
            {
                "id": spend.id,
                "clan_id": spend.clan_id,
                "origin": spend.origin,
                "spent_by_user_id": spend.spent_by_user_id,
                "spent_at": spend.spent_at,
                "recover_at": spend.recover_at,
                "level_snapshot": spend.level_snapshot,
                "capacity_snapshot": spend.capacity_snapshot,
                "campaign_rule_set_id": spend.campaign_rule_set_id,
                "rule_version": spend.rule_version,
                "refunded_at": spend.refunded_at,
                "refunded_by_user_id": spend.refunded_by_user_id,
                "refund_reason": spend.refund_reason,
            }
            for spend in sorted(war.attack_point_spends, key=lambda item: item.id)
        ],
        "level_events": [
            {
                "id": event.id,
                "clan_id": event.clan_id,
                "previous_level": event.previous_level,
                "new_level": event.new_level,
                "active_member_count": event.active_member_count,
                "territory_count": event.territory_count,
                "influence": event.influence,
                "campaign_rule_set_id": event.campaign_rule_set_id,
                "rule_version": event.rule_version,
                "reason": event.reason,
                "occurred_at": event.occurred_at,
            }
            for event in (
                db.query(ClanLevelEvent)
                .filter(
                    ClanLevelEvent.clan_id.in_(
                        tuple(
                            clan_id
                            for clan_id in (
                                war.attacking_clan_id,
                                war.defending_clan_id,
                            )
                            if clan_id is not None
                        )
                    )
                )
                .order_by(ClanLevelEvent.occurred_at, ClanLevelEvent.id)
                .all()
            )
        ],
        "audit_entries": [
            {
                "id": entry.id,
                "actor_user_id": entry.actor_user_id,
                "action": entry.action,
                "before_data": entry.before_data,
                "after_data": entry.after_data,
                "reason": entry.reason,
                "created_at": entry.created_at,
            }
            for entry in (
                db.query(AdminAuditLog)
                .filter(
                    AdminAuditLog.entity_type == "clan_war",
                    AdminAuditLog.entity_id == str(war.id),
                )
                .order_by(AdminAuditLog.created_at, AdminAuditLog.id)
                .all()
            )
        ],
    }
    return payload
