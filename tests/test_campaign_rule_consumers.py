import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.campaign_rules import RULE_DEFINITIONS, default_campaign_rule_values
from app.models.campaign import CampaignSeason
from app.models.clan import Clan, ClanMembershipPeriod
from app.models.external_identity import ExternalPlayerIdentity
from app.models.match import Match
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar, ClanWarMatchResult
from app.services.campaign_history_service import CampaignHistoryService
from app.services.campaign_rule_service import CampaignRuleService
from app.services.match_eligibility_service import ranked_match_rejection_reason
from app.services.war_service import ClanWarService


def _verified_user(db, user_id, username):
    user = User(
        id=user_id,
        username=username,
        email=f"{username}@example.com",
        hashed_password="unused",
        is_claimed=True,
    )
    db.add(user)
    db.flush()
    db.add(
        ExternalPlayerIdentity(
            user_id=user.id,
            external_uuid=f"uuid-{username}",
            current_nickname=username,
            verification_status="verified",
        )
    )
    return user


def _ranked_match(match_id, winner, loser, played_at, duration="00:10:00"):
    return Match(
        match_id=match_id,
        winner_player=winner.username,
        winner_faction="Gondor",
        loser_player=loser.username,
        loser_faction="Mordor",
        match_date=played_at,
        duration=duration,
        game_mode="1 versus 1",
        gamemode_name="1 versus 1",
        elo_delta=12,
        is_valid=True,
        map_name="Fornost",
        patch_version="Patch 2.02",
        rating_patch_family="patch_202",
        winner_elo=1000,
        loser_elo=1000,
    )


def test_match_eligibility_uses_supplied_minimum_duration():
    match = _ranked_match(
        "duration-rules",
        User(username="winner"),
        User(username="loser"),
        datetime.now(timezone.utc),
        duration="00:05:00",
    )
    defaults = default_campaign_rule_values()
    stricter = {**defaults, "WAR_MIN_MATCH_DURATION_SECONDS": 600}

    assert ranked_match_rejection_reason(match, rules=defaults) is None
    assert ranked_match_rejection_reason(match, rules=stricter) == "Матч короче 10 минут"


def test_minimum_duration_boundary_is_one_minute():
    match = _ranked_match('one-minute', User(username='winner'), User(username='loser'), datetime.now(timezone.utc), duration='00:00:59')
    rules = default_campaign_rule_values()
    assert rules['WAR_MIN_MATCH_DURATION_SECONDS'] == 60
    assert ranked_match_rejection_reason(match, rules=rules) == 'Матч короче 1 минуты'
    for duration in ['00:01:00', '00:01:59', '00:02:00']:
        match.duration = duration
        assert ranked_match_rejection_reason(match, rules=rules) is None


def test_one_minute_rule_does_not_requalify_old_matches(monkeypatch):
    from app.config import settings
    effective_at = datetime(2026, 9, 21, 21, tzinfo=timezone.utc)
    monkeypatch.setattr(settings, 'WAR_MIN_MATCH_DURATION_EFFECTIVE_AT', effective_at)
    rules = default_campaign_rule_values()
    match = _ranked_match('duration-cutover', User(username='winner'), User(username='loser'), effective_at - timedelta(seconds=1), duration='00:01:00')
    assert ranked_match_rejection_reason(match, rules=rules) == 'Матч короче 2 минут'
    match.match_date = effective_at
    assert ranked_match_rejection_reason(match, rules=rules) is None
    match.duration = '00:00:59'
    assert ranked_match_rejection_reason(match, rules=rules) == 'Матч короче 1 минуты'


def test_next_war_score_uses_the_active_campaign_rule_version(db):
    played_at = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    winner = _verified_user(db, 1, "rule-winner")
    loser = _verified_user(db, 2, "rule-loser")
    attacker = Clan(id=10, name="Rule attackers", leader_id=winner.id)
    defender = Clan(id=11, name="Rule defenders", leader_id=loser.id)
    db.add_all([attacker, defender])
    db.flush()
    db.add_all(
        [
            ClanMembershipPeriod(
                user_id=winner.id,
                clan_id=attacker.id,
                started_at=played_at - timedelta(days=1),
            ),
            ClanMembershipPeriod(
                user_id=loser.id,
                clan_id=defender.id,
                started_at=played_at - timedelta(days=1),
            ),
        ]
    )
    territory = Territory(
        id=10,
        name="Rule territory",
        region="test",
        svg_path_data="M 0 0",
        owner_clan_id=defender.id,
    )
    db.add(territory)
    db.flush()
    war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=attacker.id,
        defending_clan_id=defender.id,
        war_type="territory_attack",
        status="active",
        started_at=played_at - timedelta(hours=1),
        ends_at=played_at + timedelta(days=4),
        attacker_power=0,
        defender_power=0,
    )
    match = _ranked_match("active-rule-score", winner, loser, played_at)
    db.add_all([war, match])
    db.flush()
    rules = CampaignRuleService()
    active = rules.get_active(db)
    rules.create_version(
        db,
        expected_version=active.version,
        changes={
            "WAR_ELO_BASE_POINTS": 20,
            "WAR_ELO_MIN_POINTS": 1,
            "WAR_ELO_MAX_POINTS": 100,
        },
        actor_user_id=winner.id,
        reason="Test future war score",
        commit=True,
    )

    ClanWarService().record_match_result(
        db,
        winner.username,
        loser.username,
        played_at,
        match=match,
    )

    result = db.query(ClanWarMatchResult).filter_by(war_id=war.id).one()
    assert result.is_counted is True
    assert result.winner_base_points == 20


def test_season_stores_the_complete_public_rule_snapshot(db):
    season = CampaignHistoryService().create_season(
        db,
        starting_influence=100,
        reset_development=True,
        actor_user_id=None,
        starts_at=datetime.now(timezone.utc),
    )

    stored = db.query(CampaignSeason).filter_by(id=season.id).one().rules_snapshot
    assert stored["version"] == 1
    assert stored["values"]["WAR_DURATION_HOURS"] == 60
    assert stored["values"]["CARAVAN_BASE_GOLD_FEE"] == 7
    assert set(stored["values"]) == set(RULE_DEFINITIONS)


def test_pure_rule_consumers_do_not_read_gameplay_settings_or_legacy_elo_fallbacks():
    root = Path(__file__).parents[1]
    gameplay_references = {
        f"settings.{key}" for key in RULE_DEFINITIONS
    }

    for service_path in (root / "app" / "services").glob("*.py"):
        source = service_path.read_text(encoding="utf-8")
        for reference in gameplay_references:
            assert reference not in source
        assert "CLAN_ATTACK_COOLDOWN =" not in source
        assert "CLAN_ATTACK_COOLDOWN_SECONDS =" not in source
        assert re.search(
            r"from app\.services\.clan_attack_service import .*\bCLAN_ATTACK_COOLDOWN\b",
            source,
        ) is None
    for name in ("war_service.py", "ladder_service.py"):
        source = (root / "app" / "services" / name).read_text(encoding="utf-8")
        assert "or 1000" not in source
