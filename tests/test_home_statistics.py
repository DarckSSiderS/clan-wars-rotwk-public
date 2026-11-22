from app.api.v1.statistics import get_home_statistics
from datetime import datetime, timedelta, timezone

from app.models.clan import Clan, ClanMember
from app.models.campaign import CampaignSeason
from app.models.external_identity import ExternalPlayerIdentity
from app.models.role import Role
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.models.user import User
from app.models.war import ClanWar


def _user(db, user_id, username, role):
    user = User(
        id=user_id,
        username=username,
        email=f"{username}@example.test",
        hashed_password="unused",
        role=role,
        is_active=True,
        is_claimed=True,
    )
    db.add(user)
    db.flush()
    return user


def test_home_statistics_count_all_registered_players_and_public_clans(db):
    role = Role(name="user")
    db.add(role)
    db.flush()
    verified = _user(db, 1, "verified", role)
    pending = _user(db, 2, "pending", role)
    no_identity = _user(db, 3, "no-identity", role)
    disabled = _user(db, 4, "disabled", role)
    disabled.is_active = False
    generated_profile = _user(db, 5, "generated-profile", role)
    generated_profile.is_claimed = False

    db.add_all(
        [
            ExternalPlayerIdentity(
                user_id=verified.id,
                source="bfmeladder",
                external_uuid="verified-uuid",
                current_nickname=verified.username,
                verification_status="verified",
            ),
            ExternalPlayerIdentity(
                user_id=pending.id,
                source="bfmeladder",
                external_uuid="pending-uuid",
                current_nickname=pending.username,
                verification_status="pending",
            ),
        ]
    )
    public_clan = Clan(
        id=10,
        name="Public",
        leader_id=verified.id,
        territory_points=250,
    )
    admin_clan = Clan(
        id=11,
        name="Admin",
        leader_id=pending.id,
        territory_points=9999,
        is_admin_clan=True,
    )
    empty_clan = Clan(
        id=12,
        name="Empty",
        leader_id=no_identity.id,
        territory_points=500,
    )
    archived_clan = Clan(
        id=13,
        name="Archived",
        leader_id=no_identity.id,
        territory_points=1000,
        is_deleted=True,
    )
    db.add_all([public_clan, admin_clan, empty_clan, archived_clan])
    db.flush()
    db.add_all(
        [
            ClanMember(clan_id=public_clan.id, user_id=verified.id),
            ClanMember(clan_id=admin_clan.id, user_id=pending.id),
            ClanMember(clan_id=archived_clan.id, user_id=no_identity.id),
        ]
    )
    db.commit()

    result = get_home_statistics(db)

    assert result["clan_players"] == 1
    assert "verified_players" not in result
    assert result["total_clans"] == 1
    assert [clan["name"] for clan in result["top_clans"]] == ["Public"]


def test_home_statistics_return_live_campaign_summary(db):
    role = Role(name="user")
    db.add(role)
    db.flush()
    attacker_user = _user(db, 11, "attacker", role)
    defender_user = _user(db, 12, "defender", role)

    attacker = Clan(
        id=21,
        name="Attackers",
        leader_id=attacker_user.id,
        territory_points=300,
        map_color="#b83b3b",
    )
    defender = Clan(
        id=22,
        name="Defenders",
        leader_id=defender_user.id,
        territory_points=250,
        map_color="#3b72b8",
    )
    db.add_all([attacker, defender])
    db.flush()
    db.add_all(
        [
            ClanMember(clan_id=attacker.id, user_id=attacker_user.id),
            ClanMember(clan_id=defender.id, user_id=defender_user.id),
        ]
    )

    source = Territory(
        id=31,
        name="Source",
        region="Test",
        svg_path_data="M 0 0",
        owner_clan_id=attacker.id,
        status="active",
    )
    target = Territory(
        id=32,
        name="Target",
        region="Test",
        svg_path_data="M 1 1",
        owner_clan_id=defender.id,
        status="contested",
    )
    neutral = Territory(
        id=33,
        name="Neutral",
        region="Test",
        svg_path_data="M 2 2",
        status="neutral",
    )
    hidden = Territory(
        id=34,
        name="Admin island",
        region="Test",
        svg_path_data="M 3 3",
        status="active",
        is_playable=False,
    )
    db.add_all([source, target, neutral, hidden])
    db.flush()

    war = ClanWar(
        id=41,
        territory_id=target.id,
        source_territory_id=source.id,
        attacking_clan_id=attacker.id,
        defending_clan_id=defender.id,
        war_type="territory_attack",
        status="active",
        started_at=datetime.utcnow(),
        ends_at=datetime.utcnow() + timedelta(days=4),
        attack_route="land",
    )
    db.add(war)
    db.add(
        TerritoryOwnershipHistory(
            territory_id=source.id,
            clan_id=attacker.id,
            started_at=datetime.utcnow() - timedelta(hours=6),
            war_id=war.id,
            reason="war_victory",
        )
    )
    db.commit()

    result = get_home_statistics(db)

    assert result["territories"] == {
        "total": 3,
        "occupied": 2,
        "contested": 1,
        "free": 1,
    }
    assert result["active_wars"][0]["id"] == war.id
    assert result["active_wars"][0]["territory_name"] == "Target"
    assert result["active_wars"][0]["territory_svg_path_data"] == "M 1 1"
    assert result["active_wars"][0]["attacking_clan"]["name"] == "Attackers"
    assert result["active_wars"][0]["defending_clan"]["name"] == "Defenders"
    assert result["recent_territory_changes"] == [
        {
            "territory_id": source.id,
            "territory_name": "Source",
            "territory_svg_path_data": "M 0 0",
            "clan_id": attacker.id,
            "clan_name": "Attackers",
            "clan_avatar_url": None,
            "clan_map_color": "#b83b3b",
            "captured_at": result["recent_territory_changes"][0]["captured_at"],
            "war_id": war.id,
        }
    ]


def test_home_statistics_include_active_season_and_calendar_progress(db):
    role = Role(name="user")
    user = _user(db, 51, "season-player", role)
    clan = Clan(id=52, name="Season clan", leader_id=user.id)
    db.add(clan)
    db.flush()
    db.add(ClanMember(clan_id=clan.id, user_id=user.id))
    now = datetime.now(timezone.utc)
    season = CampaignSeason(
        number=4,
        name="Пепел Андуина",
        status="active",
        starts_at=now - timedelta(days=5),
        ends_at=now + timedelta(days=5),
    )
    db.add(season)
    db.commit()

    result = get_home_statistics(db)

    assert result["season"]["id"] == season.id
    assert result["season"]["number"] == 4
    assert result["season"]["name"] == "Пепел Андуина"
    assert 49 <= result["season"]["progress_percent"] <= 51
    assert result["season"]["goals"][2] == {
        "key": "campaign_clans",
        "current": 1,
        "target": None,
    }
