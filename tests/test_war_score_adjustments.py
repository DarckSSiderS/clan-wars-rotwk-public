from uuid import uuid4
import pytest
from fastapi import HTTPException
from app.api.v1.admin import adjust_war_points, WarScoreAdjustmentRequest, review_admin_war_match, WarMatchReviewRequest
from app.models.war import ClanWarMatchResult
from app.models.war_adjustment import WarScoreAdjustment
from app.services.war_service import ClanWarService
from tests.test_admin_dashboard import _admin, _active_war


@pytest.mark.parametrize('status', ['active', 'completed', 'canceled'])
def test_manual_points_survive_recalculation_and_are_idempotent(db, status):
    admin = _admin(db)
    war, attacker, _, territory = _active_war(db, admin)
    war.status = status
    db.commit()
    owner = territory.owner_clan_id
    service = ClanWarService()
    score = lambda: next(s['points'] for s in service.serialize_war(db, war)['clan_scores'] if s['clan_id'] == attacker.id)
    before = score()
    request = WarScoreAdjustmentRequest(clan_id=attacker.id, points=25, reason='Replay correction', request_id=uuid4())
    adjust_war_points(war.id, request, admin, db)
    adjust_war_points(war.id, request, admin, db)
    assert db.query(WarScoreAdjustment).count() == 1
    assert score() == before + 25
    service.recalculate_active_war(db, war.id, allow_finished=True)
    assert score() == before + 25
    assert war.status == status
    assert territory.owner_clan_id == owner
    result = db.query(ClanWarMatchResult).one()
    review_admin_war_match(war.id, result.id, WarMatchReviewRequest(mode='exclude', reason='Invalid replay'), admin, db)
    assert score() == 25
    review_admin_war_match(war.id, result.id, WarMatchReviewRequest(mode='count', reason='Verified replay'), admin, db)
    assert score() == before + 25
    assert war.status == status
    assert territory.owner_clan_id == owner


def test_adjustment_rejects_wrong_side_and_request_reuse(db):
    admin = _admin(db)
    war, attacker, _, _ = _active_war(db, admin)
    request = WarScoreAdjustmentRequest(clan_id=attacker.id, points=10, reason='Score correction', request_id=uuid4())
    adjust_war_points(war.id, request, admin, db)
    for changes, code in [({'clan_id': 99999}, 422), ({'points': 0}, 422), ({'points': 20}, 409)]:
        with pytest.raises(HTTPException) as error:
            adjust_war_points(war.id, request.model_copy(update=changes), admin, db)
        assert error.value.status_code == code


def test_admin_can_count_recorded_match_when_automatic_eligibility_fails(db, monkeypatch):
    admin = _admin(db)
    war, attacker, _, _ = _active_war(db, admin)
    result = db.query(ClanWarMatchResult).one()
    original = ClanWarService._match_team_contexts
    def no_eligible_players(self, *args, **kwargs):
        contexts = original(self, *args, **kwargs)
        for team in contexts.values():
            team['verified_clan_users'] = {}
        return contexts
    monkeypatch.setattr(ClanWarService, '_match_team_contexts', no_eligible_players)
    ClanWarService().recalculate_active_war(db, war.id)
    assert not result.is_counted
    review_admin_war_match(war.id, result.id, WarMatchReviewRequest(mode='count', reason='Verified membership manually'), admin, db)
    assert result.is_counted
    assert result.winner_total_points > 0


def test_one_minute_rule_update_is_idempotent_and_keeps_archived_rules(db):
    from scripts.update_minimum_match_duration import apply_minimum_duration
    from app.core.campaign_rules import default_campaign_rule_values
    from app.models.war import ClanWar
    from app.models.campaign import CampaignRuleSet
    from app.services.campaign_rule_service import CampaignRuleService
    admin = _admin(db)
    war, attacker, _, territory = _active_war(db, admin)
    active_rules = CampaignRuleService().get_active(db)
    db.get(CampaignRuleSet, active_rules.id).values = {**active_rules.values, 'WAR_MIN_MATCH_DURATION_SECONDS': 120}
    war.rules_snapshot = {**default_campaign_rule_values(), 'WAR_MIN_MATCH_DURATION_SECONDS': 120}
    archived = ClanWar(territory_id=territory.id, attacking_clan_id=attacker.id, war_type='neutral_capture', status='completed', rules_snapshot=dict(war.rules_snapshot))
    db.add(archived)
    result = db.query(ClanWarMatchResult).one()
    result.match.duration = '00:01:00'
    db.commit()
    ClanWarService().recalculate_active_war(db, war.id)
    assert not result.is_counted
    assert apply_minimum_duration(db, actor_user_id=admin.id) == [war.id]
    assert not result.is_counted
    assert result.winner_total_points == 0
    assert war.rules_snapshot['WAR_MIN_MATCH_DURATION_SECONDS'] == 60
    assert CampaignRuleService().get_active(db).version == active_rules.version + 1
    assert archived.rules_snapshot['WAR_MIN_MATCH_DURATION_SECONDS'] == 120
    assert apply_minimum_duration(db, actor_user_id=admin.id) == []
