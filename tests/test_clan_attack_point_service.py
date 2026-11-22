from datetime import datetime, timedelta, timezone

import pytest

from app.core.campaign_rules import default_campaign_rule_values
from app.models.campaign import CampaignRuleSet
from app.models.clan import Clan
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar
from app.services.campaign_rule_service import CampaignRuleService
from app.services.clan_attack_point_service import (
    AttackPointsExhausted,
    ClanAttackPointService,
)


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def _context(db, *, cooldown=None):
    leader = User(username="leader", email="leader@example.test", hashed_password="x")
    db.add(leader)
    db.flush()
    clan = Clan(name="Attackers", leader_id=leader.id, level=1)
    db.add(clan)
    db.flush()
    territory = Territory(name="Target", region="Test", svg_path_data="M0 0")
    values = default_campaign_rule_values()
    if cooldown is not None:
        values["CLAN_ATTACK_COOLDOWN_HOURS"] = cooldown
    rule_row = CampaignRuleSet(version=1, values=values, is_active=True, reason="test")
    db.add_all([territory, rule_row])
    db.flush()
    return leader, clan, territory, CampaignRuleService().get_active(db)


def _war(db, clan, territory, *, suffix, started_at=NOW):
    war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=clan.id,
        war_type="neutral_capture",
        status="active",
        started_at=started_at,
        ends_at=started_at + timedelta(hours=60),
        scoring_version=f"elo_team_v3_squads-{suffix}",
    )
    db.add(war)
    db.flush()
    return war


@pytest.mark.parametrize("capacity", [1, 2, 3, 4, 5])
def test_empty_clan_has_full_configured_capacity(db, capacity):
    _, clan, _, _ = _context(db)

    status = ClanAttackPointService().status(db, clan, capacity=capacity, now=NOW)

    assert status.capacity == capacity
    assert status.available == capacity
    assert status.recovering == 0
    assert status.next_attack_at is None
    assert clan.next_attack_at is None


def test_each_spend_recovers_on_its_own_schedule(db):
    leader, clan, territory, rule_set = _context(db)
    service = ClanAttackPointService()
    first_war = _war(db, clan, territory, suffix="one")
    second_war = _war(db, clan, territory, suffix="two", started_at=NOW + timedelta(hours=1))
    first = service.spend(
        db,
        clan,
        war=first_war,
        actor_user_id=leader.id,
        level=2,
        capacity=2,
        rule_set=rule_set,
        now=NOW,
    )
    second = service.spend(
        db,
        clan,
        war=second_war,
        actor_user_id=leader.id,
        level=2,
        capacity=2,
        rule_set=rule_set,
        now=NOW + timedelta(hours=1),
    )

    full = service.status(db, clan, capacity=2, now=NOW + timedelta(hours=2))
    partly_recovered = service.status(
        db, clan, capacity=2, now=NOW + timedelta(hours=60, minutes=30)
    )

    assert first.recover_at == NOW + timedelta(hours=60)
    assert second.recover_at == NOW + timedelta(hours=61)
    assert full.available == 0
    assert full.next_attack_at == first.recover_at
    assert partly_recovered.available == 1
    assert partly_recovered.recovering == 1
    assert partly_recovered.next_attack_at is None

    before = service.status(db, clan, capacity=2, now=NOW + timedelta(hours=60, microseconds=-1))
    boundary = service.status(db, clan, capacity=2, now=NOW + timedelta(hours=60))
    complete = service.status(db, clan, capacity=2, now=NOW + timedelta(hours=61))
    later = service.status(db, clan, capacity=2, now=NOW + timedelta(days=10))
    assert (before.available, boundary.available, complete.available, later.available) == (0, 1, 2, 2)
    assert complete.recoveries == ()


def test_level_down_blocks_excess_without_canceling_active_wars(db):
    leader, clan, territory, rule_set = _context(db)
    service = ClanAttackPointService()
    wars = [_war(db, clan, territory, suffix=str(index)) for index in range(3)]
    for war in wars:
        service.spend(
            db,
            clan,
            war=war,
            actor_user_id=leader.id,
            level=3,
            capacity=3,
            rule_set=rule_set,
            now=NOW,
        )

    status = service.status(db, clan, capacity=1, now=NOW + timedelta(hours=1))

    assert status.available == 0
    assert status.recovering == 3
    assert status.blocked == 2
    assert all(war.status == "active" for war in wars)


def test_second_spend_fails_after_capacity_is_exhausted(db):
    leader, clan, territory, rule_set = _context(db)
    service = ClanAttackPointService()
    service.spend(
        db,
        clan,
        war=_war(db, clan, territory, suffix="one"),
        actor_user_id=leader.id,
        level=1,
        capacity=1,
        rule_set=rule_set,
        now=NOW,
    )

    with pytest.raises(AttackPointsExhausted):
        service.spend(
            db,
            clan,
            war=_war(db, clan, territory, suffix="two"),
            actor_user_id=leader.id,
            level=1,
            capacity=1,
            rule_set=rule_set,
            now=NOW,
        )


def test_refund_for_war_only_refunds_that_wars_spend(db):
    leader, clan, territory, rule_set = _context(db)
    service = ClanAttackPointService()
    first_war = _war(db, clan, territory, suffix="one")
    second_war = _war(db, clan, territory, suffix="two")
    first = service.spend(
        db,
        clan,
        war=first_war,
        actor_user_id=leader.id,
        level=2,
        capacity=2,
        rule_set=rule_set,
        now=NOW,
    )
    second = service.spend(
        db,
        clan,
        war=second_war,
        actor_user_id=leader.id,
        level=2,
        capacity=2,
        rule_set=rule_set,
        now=NOW,
    )

    refunded = service.refund_for_war(
        db,
        first_war,
        actor_user_id=leader.id,
        reason="war_canceled",
        now=NOW + timedelta(hours=1),
    )
    status = service.status(db, clan, capacity=2, now=NOW + timedelta(hours=1))

    assert refunded.id == first.id
    assert first.refunded_at is not None
    assert second.refunded_at is None
    assert status.available == 1


def test_extending_war_does_not_move_point_recovery(db):
    leader, clan, territory, rule_set = _context(db)
    service = ClanAttackPointService()
    war = _war(db, clan, territory, suffix="one")
    spend = service.spend(
        db,
        clan,
        war=war,
        actor_user_id=leader.id,
        level=1,
        capacity=1,
        rule_set=rule_set,
        now=NOW,
    )
    original_recovery = spend.recover_at

    war.ends_at += timedelta(days=2)
    db.flush()

    assert spend.recover_at == original_recovery


def test_legacy_next_attack_spend_is_refunded_for_v2_war(db):
    leader, clan, territory, rule_set = _context(db)
    service = ClanAttackPointService()
    war = _war(db, clan, territory, suffix="legacy")
    war.scoring_version = "elo_team_v2"
    legacy = service.create_legacy_spend(
        db,
        clan,
        recover_at=NOW + timedelta(hours=48),
        rule_set=rule_set,
        now=NOW - timedelta(hours=48),
    )

    refunded = service.refund_for_war(
        db,
        war,
        actor_user_id=leader.id,
        reason="legacy_war_canceled",
        now=NOW,
    )

    assert refunded.id == legacy.id
    assert legacy.refunded_at == NOW
    assert clan.next_attack_at is None
