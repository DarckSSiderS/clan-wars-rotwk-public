from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.campaign_rules import default_campaign_rule_values
from app.models.campaign import CampaignRuleSet
from app.models.clan import Clan
from app.models.clan_warfare import ClanAttackPointSpend, ClanLevelEvent
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar
from app.models.war_deployment import WarDeployment, WarDeploymentMember


def _war_fixture(db):
    leader_a = User(username="leader-a", email="leader-a@example.test", hashed_password="x")
    leader_b = User(username="leader-b", email="leader-b@example.test", hashed_password="x")
    fighter = User(username="fighter", email="fighter@example.test", hashed_password="x")
    db.add_all([leader_a, leader_b, fighter])
    db.flush()

    clan_a = Clan(name="Clan A", leader_id=leader_a.id)
    clan_b = Clan(name="Clan B", leader_id=leader_b.id)
    db.add_all([clan_a, clan_b])
    db.flush()

    territory = Territory(name="Test land", region="Test", svg_path_data="M0 0")
    rule_set = CampaignRuleSet(
        version=1,
        values=default_campaign_rule_values(),
        is_active=True,
        reason="test",
    )
    db.add_all([territory, rule_set])
    db.flush()

    war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=clan_a.id,
        defending_clan_id=clan_b.id,
        war_type="territory_attack",
        campaign_rule_set_id=rule_set.id,
        rules_snapshot=rule_set.values,
        scoring_version="elo_team_v3_squads",
    )
    db.add(war)
    db.commit()
    return leader_a, leader_b, fighter, clan_a, clan_b, territory, rule_set, war


def _spend(*, clan, war, leader, rule_set, now):
    return ClanAttackPointSpend(
        clan_id=clan.id,
        war_id=war.id,
        spent_by_user_id=leader.id,
        origin="war",
        spent_at=now,
        recover_at=now + timedelta(hours=60),
        level_snapshot=1,
        capacity_snapshot=1,
        campaign_rule_set_id=rule_set.id,
        rule_version=rule_set.version,
    )


def test_neutral_challenge_allows_one_spend_per_clan(db):
    leader_a, leader_b, _, clan_a, clan_b, _, rule_set, war = _war_fixture(db)
    now = datetime.now(timezone.utc)
    db.add_all(
        [
            _spend(clan=clan_a, war=war, leader=leader_a, rule_set=rule_set, now=now),
            _spend(clan=clan_b, war=war, leader=leader_b, rule_set=rule_set, now=now),
        ]
    )
    db.commit()

    assert db.query(ClanAttackPointSpend).count() == 2
    assert len(war.attack_point_spends) == 2


def test_same_clan_cannot_spend_twice_for_one_war(db):
    leader_a, _, _, clan_a, _, _, rule_set, war = _war_fixture(db)
    now = datetime.now(timezone.utc)
    db.add_all(
        [
            _spend(clan=clan_a, war=war, leader=leader_a, rule_set=rule_set, now=now),
            _spend(clan=clan_a, war=war, leader=leader_a, rule_set=rule_set, now=now),
        ]
    )

    with pytest.raises(IntegrityError):
        db.commit()


def test_active_attack_member_is_unique_but_released_history_is_allowed(db):
    leader_a, leader_b, fighter, clan_a, clan_b, territory, rule_set, war = _war_fixture(db)
    now = datetime.now(timezone.utc)
    first = WarDeployment(
        war_id=war.id,
        clan_id=clan_a.id,
        claim_sequence=1,
        source_territory_id=territory.id,
        territory_count_snapshot=1,
        defense_rule="squad_if_challenged",
        initial_role="attacker",
        current_role="attacker",
        eligibility_scope="squad",
        assigned_by_user_id=leader_a.id,
        assigned_at=now,
        campaign_rule_set_id=rule_set.id,
        rule_version=rule_set.version,
    )
    db.add(first)
    db.flush()
    db.add(
        WarDeploymentMember(
            deployment_id=first.id,
            user_id=fighter.id,
            external_uuid_snapshot="uuid-fighter",
            nickname_snapshot="Fighter",
            username_snapshot=fighter.username,
            membership_started_at=now - timedelta(days=10),
            assigned_at=now,
        )
    )
    db.commit()

    second_war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=clan_b.id,
        war_type="neutral_capture",
        campaign_rule_set_id=rule_set.id,
        rules_snapshot=rule_set.values,
        scoring_version="elo_team_v3_squads",
    )
    db.add(second_war)
    db.flush()
    second = WarDeployment(
        war_id=second_war.id,
        clan_id=clan_b.id,
        claim_sequence=1,
        territory_count_snapshot=0,
        defense_rule="whole_clan_if_challenged",
        initial_role="attacker",
        current_role="attacker",
        eligibility_scope="squad",
        assigned_by_user_id=leader_b.id,
        assigned_at=now,
        campaign_rule_set_id=rule_set.id,
        rule_version=rule_set.version,
    )
    db.add(second)
    db.flush()
    db.add(
        WarDeploymentMember(
            deployment_id=second.id,
            user_id=fighter.id,
            external_uuid_snapshot="uuid-fighter",
            nickname_snapshot="Fighter renamed",
            username_snapshot=fighter.username,
            membership_started_at=now - timedelta(days=10),
            assigned_at=now,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()
    first_member = db.query(WarDeploymentMember).filter_by(deployment_id=first.id).one()
    first_member.released_at = now
    db.flush()
    db.add(second)
    db.flush()
    db.add(
        WarDeploymentMember(
            deployment_id=second.id,
            user_id=fighter.id,
            external_uuid_snapshot="uuid-fighter",
            nickname_snapshot="Fighter renamed",
            username_snapshot=fighter.username,
            membership_started_at=now - timedelta(days=10),
            assigned_at=now,
        )
    )
    db.commit()

    assert len(war.deployments) == 1
    assert db.query(WarDeploymentMember).filter_by(user_id=fighter.id).count() == 2


def test_level_event_is_related_to_clan_and_rule_version(db):
    _, _, _, clan_a, _, _, rule_set, _ = _war_fixture(db)
    event = ClanLevelEvent(
        clan_id=clan_a.id,
        previous_level=1,
        new_level=2,
        active_member_count=7,
        territory_count=1,
        influence=150,
        campaign_rule_set_id=rule_set.id,
        rule_version=rule_set.version,
        reason="thresholds_recalculated",
    )
    db.add(event)
    db.commit()

    assert event in clan_a.level_events
    assert event.campaign_rule_set.version == 1


def test_clan_warfare_migration_follows_campaign_rules_head():
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "c9d0e1f2a3b4_add_clan_warfare_deployments.py"
    )
    spec = importlib.util.spec_from_file_location("clan_warfare_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "c9d0e1f2a3b4"
    assert migration.down_revision == "b8c9d0e1f2a3"
