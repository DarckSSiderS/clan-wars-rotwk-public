"""Update rule snapshots without recalculating any existing match or score."""
from app.models.war import ClanWar
from app.services.campaign_rule_service import CampaignRuleService
from app.services.operation_service import AdminAuditService
from app.services.war_service import ClanWarService


def apply_minimum_duration(db, *, actor_user_id):
    service = ClanWarService()
    active = db.query(ClanWar).filter_by(status='active').all()
    service.economy.ledger.lock_clans(db, [clan_id for war in active for clan_id in (war.attacking_clan_id, war.defending_clan_id) if clan_id])
    rules_service = CampaignRuleService()
    current = rules_service.get_active(db)
    reason = 'Minimum ranked match duration changed to 60 seconds by project owner'
    if current.values['WAR_MIN_MATCH_DURATION_SECONDS'] != 60:
        rules_service.create_version(db, expected_version=current.version,
            changes={'WAR_MIN_MATCH_DURATION_SECONDS': 60}, actor_user_id=actor_user_id,
            reason=reason, commit=False)
    updated = []
    for war in db.query(ClanWar).filter_by(status='active').order_by(ClanWar.id).with_for_update().all():
        if war.rules_snapshot and war.rules_snapshot.get('WAR_MIN_MATCH_DURATION_SECONDS') == 60:
            continue
        before = (war.rules_snapshot or current.values)['WAR_MIN_MATCH_DURATION_SECONDS']
        war.rules_snapshot = {**(war.rules_snapshot or current.values), 'WAR_MIN_MATCH_DURATION_SECONDS': 60}
        db.flush()
        AdminAuditService().record(db, actor_user_id=actor_user_id, action='war_minimum_duration_updated',
            entity_type='clan_war', entity_id=war.id, before_data={'minimum_seconds': before},
            after_data={'minimum_seconds': 60}, reason=reason)
        updated.append(war.id)
    db.commit()
    return updated
