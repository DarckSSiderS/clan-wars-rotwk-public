from datetime import datetime, timedelta, timezone

import pytest

from app.core.campaign_rules import default_campaign_rule_values
from app.models.campaign import CampaignRuleSet
from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.external_identity import ExternalPlayerIdentity
from app.models.match import Match, MatchParticipant
from app.models.territory import Territory
from app.models.user import User
from app.services.campaign_rule_service import CampaignRuleService
from app.services.clan_level_service import ClanLevelService


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def test_public_clan_responses_calculate_current_level_without_writing_events(db):
    from app.api.v1.clans import read_clan, read_clans
    from app.models.clan_warfare import ClanLevelEvent

    _rule_set(db)
    clan = _clan(db, level=1, influence=230)
    _territories(db, clan, 4)
    _current_members(db, clan, 17)
    db.commit()
    assert read_clan(clan.id, db=db).level == 3
    assert read_clans(db=db)[0].level == 3
    assert clan.level == 1
    assert db.query(ClanLevelEvent).count() == 0


def _rule_set(db, **overrides):
    values = default_campaign_rule_values()
    values.update(overrides)
    row = CampaignRuleSet(version=1, values=values, is_active=True, reason="test")
    db.add(row)
    db.flush()
    return CampaignRuleService().get_active(db)


def _clan(db, *, level=1, influence=0):
    leader = User(username="leader", email="leader@example.test", hashed_password="x")
    db.add(leader)
    db.flush()
    clan = Clan(name="Test clan", leader_id=leader.id, level=level, territory_points=influence)
    db.add(clan)
    db.flush()
    return clan


def _territories(db, clan, count):
    for index in range(count):
        db.add(
            Territory(
                name=f"Land {index}",
                region="Test",
                svg_path_data=f"M{index} 0",
                owner_clan_id=clan.id,
            )
        )
    db.flush()


def _current_members(db, clan, count):
    for index in range(count):
        user = User(
            username=f"level-member-{clan.id}-{index}",
            email=f"level-member-{clan.id}-{index}@example.test",
            hashed_password="x",
        )
        db.add(user)
        db.flush()
        db.add(ClanMember(user_id=user.id, clan_id=clan.id, joined_at=NOW))
    db.flush()


@pytest.mark.parametrize(
    ("expected_level", "active", "territories", "influence"),
    [
        (1, 0, 0, 0),
        (2, 11, 2, 140),
        (3, 17, 4, 230),
        (4, 22, 6, 340),
        (5, 30, 10, 500),
    ],
)
def test_level_uses_all_configured_thresholds(
    db, expected_level, active, territories, influence
):
    rule_set = _rule_set(db)
    clan = _clan(db, influence=influence)
    _territories(db, clan, territories)
    _current_members(db, clan, active)
    service = ClanLevelService()

    status = service.evaluate(db, clan, rule_set=rule_set, now=NOW, record=False)

    assert status.level == expected_level
    assert status.attack_capacity == expected_level


@pytest.mark.parametrize(
    ("active", "territories", "influence", "missing_key"),
    [
        (10, 2, 140, "active_members"),
        (11, 1, 140, "territories"),
        (11, 2, 139, "influence"),
    ],
)
def test_level_two_requires_every_threshold(
    db, active, territories, influence, missing_key
):
    rule_set = _rule_set(db)
    clan = _clan(db, influence=influence)
    _territories(db, clan, territories)
    _current_members(db, clan, active)
    service = ClanLevelService()

    status = service.evaluate(db, clan, rule_set=rule_set, now=NOW, record=False)

    assert status.level == 1
    assert status.missing[missing_key] == 1


def _member(
    db,
    clan,
    *,
    username="fighter",
    verified=True,
    joined_at=NOW - timedelta(days=40),
):
    user = User(username=username, email=f"{username}@example.test", hashed_password="x")
    db.add(user)
    db.flush()
    member = ClanMember(user_id=user.id, clan_id=clan.id, joined_at=joined_at)
    identity = ExternalPlayerIdentity(
        user_id=user.id,
        external_uuid=f"uuid-{username}",
        current_nickname=f"Nick-{username}",
        verification_status="verified" if verified else "unverified",
    )
    period = ClanMembershipPeriod(
        user_id=user.id,
        clan_id=clan.id,
        started_at=joined_at,
        started_reason="test",
    )
    db.add_all([member, identity, period])
    db.flush()
    return user, identity, period


def _match(
    db,
    identity,
    *,
    match_id,
    played_at,
    mode="2 versus 2",
    patch="Patch 2.02 (9.6.5)",
    patch_id="official-2:9.6.5",
    duration="00:03:00",
    valid=True,
    ranked=True,
    observer=False,
    with_participant=True,
):
    match = Match(
        match_id=match_id,
        winner_player=identity.current_nickname,
        winner_player_uuid=identity.external_uuid,
        winner_faction="Gondor",
        loser_player=f"Opponent-{match_id}",
        loser_player_uuid=f"opponent-{match_id}",
        loser_faction="Mordor",
        match_date=played_at,
        duration=duration,
        game_mode=mode,
        gamemode_name=mode,
        patch_name=patch,
        patch_id=patch_id,
        is_valid=valid,
        elo_delta=10 if ranked else 0,
    )
    db.add(match)
    db.flush()
    if with_participant:
        db.add(
            MatchParticipant(
                match_id=match.id,
                nickname=identity.current_nickname,
                player_uuid=identity.external_uuid,
                team=1,
                is_winner=True,
                is_observer=observer,
                old_rank=100 if ranked else None,
                new_rank=99 if ranked else None,
            )
        )
    db.flush()
    return match


def test_activity_counts_unique_valid_matches_in_both_patch_families(db):
    rule_set = _rule_set(db)
    clan = _clan(db)
    user, identity, _ = _member(db, clan)
    _match(db, identity, match_id="one", played_at=NOW - timedelta(days=1), mode="1v1")
    _match(
        db,
        identity,
        match_id="two",
        played_at=NOW - timedelta(days=2),
        mode="4 versus 4",
        patch="Ennorath 1.9.7.7d",
        patch_id="ennorath:1.9.7.7d",
    )
    _match(db, identity, match_id="three", played_at=NOW - timedelta(days=28))
    _match(db, identity, match_id="outside", played_at=NOW - timedelta(days=28, seconds=1))

    activity = ClanLevelService().activity_by_member(
        db, clan.id, rules=rule_set.values, now=NOW
    )

    assert activity[user.id] == 3


def test_activity_requires_current_verified_membership_at_match_time(db):
    rule_set = _rule_set(db)
    clan = _clan(db)
    user, identity, active_period = _member(
        db, clan, joined_at=NOW - timedelta(days=7)
    )
    unverified_user, unverified_identity, _ = _member(
        db, clan, username="unverified", verified=False
    )
    _match(db, identity, match_id="before-join", played_at=NOW - timedelta(days=8))
    _match(db, identity, match_id="during", played_at=NOW - timedelta(days=1))
    _match(
        db,
        unverified_identity,
        match_id="unverified",
        played_at=NOW - timedelta(days=1),
    )
    active_period.started_at = NOW - timedelta(hours=12)

    activity = ClanLevelService().activity_by_member(
        db, clan.id, rules=rule_set.values, now=NOW
    )

    assert activity[user.id] == 0
    assert activity[unverified_user.id] == 0


def test_activity_ignores_invalid_unranked_short_observer_and_other_patch(db):
    rule_set = _rule_set(db)
    clan = _clan(db)
    user, identity, _ = _member(db, clan)
    _match(db, identity, match_id="invalid", played_at=NOW, valid=False)
    _match(db, identity, match_id="unranked", played_at=NOW, ranked=False)
    _match(db, identity, match_id="short", played_at=NOW, duration="00:00:59")
    _match(db, identity, match_id="observer", played_at=NOW, observer=True)
    _match(
        db,
        identity,
        match_id="other-patch",
        played_at=NOW,
        patch="Age of the Ring",
        patch_id="aotr:8.3",
    )

    activity = ClanLevelService().activity_by_member(
        db, clan.id, rules=rule_set.values, now=NOW
    )

    assert activity[user.id] == 0


def test_activity_uses_legacy_nickname_only_when_uuid_rows_are_absent(db):
    rule_set = _rule_set(db)
    clan = _clan(db)
    user, identity, _ = _member(db, clan)
    legacy = _match(
        db,
        identity,
        match_id="legacy-name",
        played_at=NOW - timedelta(days=1),
        with_participant=False,
    )
    legacy.winner_player_uuid = None

    activity = ClanLevelService().activity_by_member(
        db, clan.id, rules=rule_set.values, now=NOW
    )

    assert activity[user.id] == 1


def test_current_member_of_another_clan_does_not_raise_old_clan_activity(db):
    rule_set = _rule_set(db)
    old_clan = _clan(db)
    user, identity, period = _member(db, old_clan)
    _match(db, identity, match_id="old-clan-match", played_at=NOW - timedelta(days=1))
    old_member = db.query(ClanMember).filter_by(user_id=user.id).one()
    db.delete(old_member)
    period.ended_at = NOW - timedelta(hours=12)
    new_leader = User(username="new-leader", email="new-leader@example.test", hashed_password="x")
    db.add(new_leader)
    db.flush()
    new_clan = Clan(name="New clan", leader_id=new_leader.id)
    db.add(new_clan)
    db.flush()
    db.add(ClanMember(user_id=user.id, clan_id=new_clan.id, joined_at=NOW))
    db.flush()

    activity = ClanLevelService().activity_by_member(
        db, old_clan.id, rules=rule_set.values, now=NOW
    )

    assert user.id not in activity


def test_level_event_is_recorded_only_when_level_changes(db):
    rule_set = _rule_set(db)
    clan = _clan(db)
    _territories(db, clan, 2)
    _current_members(db, clan, 11)
    clan.territory_points = 140
    service = ClanLevelService()

    first = service.evaluate(db, clan, rule_set=rule_set, now=NOW)
    second = service.evaluate(db, clan, rule_set=rule_set, now=NOW)

    assert first.level == second.level == clan.level == 2
    assert len(clan.level_events) == 1
    assert clan.level_events[0].previous_level == 1
    assert clan.level_events[0].rule_version == 1
