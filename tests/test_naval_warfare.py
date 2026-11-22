import pytest

from app.core.campaign_rules import default_campaign_rule_values
from app.core.exceptions import InsufficientPermissionsException
from app.models.clan import Clan, ClanMember
from app.models.external_identity import ExternalPlayerIdentity
from app.models.role import Role
from app.models.territory import Territory
from app.models.user import User
from app.schemas.war import ClanWarCreate
from app.services.clan_economy_service import ClanEconomyService
from app.services.war_service import ClanWarService, apply_war_power_modifier


DEFAULT_RULES = default_campaign_rule_values()


def add_clan_with_leader(db, suffix: str):
    role = Role(name=f"user-{suffix}", description="Игрок")
    leader = User(
        username=f"leader-{suffix}",
        email=f"leader-{suffix}@example.com",
        hashed_password="unused",
        role=role,
        is_active=True,
        is_claimed=True,
    )
    clan = Clan(
        name=f"Клан {suffix}",
        leader=leader,
        territory_points=5000,
        gold=10000,
        resources=10000,
        iron=1000,
        wood=1000,
        food=1000,
        mithril=1000,
    )
    db.add_all([role, leader, clan])
    db.flush()
    db.add(ClanMember(clan_id=clan.id, user_id=leader.id, rank="Глава клана"))
    squad_ids = []
    for index in range(5):
        fighter = User(
            username=f"fighter-{suffix}-{index}",
            email=f"fighter-{suffix}-{index}@example.com",
            hashed_password="unused",
            role=role,
            is_active=True,
            is_claimed=True,
        )
        db.add(fighter)
        db.flush()
        db.add_all([
            ClanMember(
                clan_id=clan.id,
                user_id=fighter.id,
                rank="Воин",
                is_warlord=index == 0,
            ),
            ExternalPlayerIdentity(
                user_id=fighter.id,
                external_uuid=f"uuid-{suffix}-{index}",
                current_nickname=f"Fighter {suffix} {index}",
                verification_status="verified",
            ),
        ])
        squad_ids.append(fighter.id)
    db.commit()
    return clan, leader, squad_ids


def add_territory(db, name: str, **values):
    territory = Territory(
        name=name,
        region="gondor",
        svg_path_data=f"M 0 0 L {len(name) + 1} 0 L 1 1 Z",
        **values,
    )
    db.add(territory)
    db.commit()
    return territory


def test_port_and_fleet_are_purchased_as_one_naval_upgrade(db):
    clan, leader, _ = add_clan_with_leader(db, "naval-upgrades")
    port = add_territory(
        db,
        "Портовая крепость",
        owner_clan_id=clan.id,
        is_coastal=True,
        has_port=True,
    )
    inland = add_territory(
        db,
        "Сухопутная крепость",
        owner_clan_id=clan.id,
        has_port=False,
    )
    service = ClanEconomyService()

    quotes = service.get_upgrade_quotes(db, port)
    assert "naval" in quotes
    assert "port" not in quotes
    assert "fleet" not in quotes

    service.upgrade_territory(db, port.id, "naval", 1, leader)
    db.refresh(port)

    assert port.port_level == 1
    assert port.fleet_level == 1
    economy = service.get_territory_economy(port, db)
    assert economy["naval_level"] == 1
    assert economy["sea_attack_bonus_percent"] == (
        DEFAULT_RULES["PORT_LEVEL_BONUS_PERCENT"]
        + DEFAULT_RULES["FLEET_LEVEL_BONUS_PERCENT"]
    )

    with pytest.raises(InsufficientPermissionsException, match="территории с портом"):
        service.upgrade_territory(db, inland.id, "naval", 1, leader)


def test_adjacent_attack_uses_military_camp_even_from_port(db):
    clan, leader, squad_ids = add_clan_with_leader(db, "land-route")
    source = add_territory(
        db,
        "Соседний порт",
        owner_clan_id=clan.id,
        is_coastal=True,
        has_port=True,
        offense_level=3,
        port_level=8,
        fleet_level=8,
    )
    target = add_territory(
        db,
        "Соседняя цель",
        is_coastal=True,
        adjacent_territory_ids=[source.id],
    )
    source.adjacent_territory_ids = [target.id]
    db.commit()

    war = ClanWarService().create_war(
        db,
        ClanWarCreate(
            territory_id=target.id,
            source_territory_id=source.id,
            squad_member_ids=squad_ids,
            warlord_user_id=squad_ids[0],
            expected_rule_version=1,
        ),
        leader,
    )

    assert war.attack_route == "land"
    assert war.attacker_power == 3 * DEFAULT_RULES["TERRITORY_LEVEL_BONUS_PERCENT"]


def test_distant_coastal_attack_uses_port_and_fleet(db):
    clan, leader, squad_ids = add_clan_with_leader(db, "sea-route")
    source = add_territory(
        db,
        "Дальний порт",
        owner_clan_id=clan.id,
        is_coastal=True,
        has_port=True,
        offense_level=9,
        port_level=3,
        fleet_level=4,
    )
    target = add_territory(
        db,
        "Заморский берег",
        is_coastal=True,
        adjacent_territory_ids=[],
    )

    war = ClanWarService().create_war(
        db,
        ClanWarCreate(
            territory_id=target.id,
            source_territory_id=source.id,
            squad_member_ids=squad_ids,
            warlord_user_id=squad_ids[0],
            expected_rule_version=1,
        ),
        leader,
    )

    assert war.attack_route == "sea"
    assert war.attacker_power == (
        3 * DEFAULT_RULES["PORT_LEVEL_BONUS_PERCENT"]
        + 4 * DEFAULT_RULES["FLEET_LEVEL_BONUS_PERCENT"]
    )


def test_failed_route_validation_does_not_consume_attack(db):
    clan, leader, squad_ids = add_clan_with_leader(db, "bad-route")
    source = add_territory(
        db,
        "Закрытая земля",
        owner_clan_id=clan.id,
        has_port=False,
    )
    target = add_territory(db, "Недостижимая земля", is_coastal=False)

    with pytest.raises(InsufficientPermissionsException, match="нет сухопутного или морского пути"):
        ClanWarService().create_war(
            db,
            ClanWarCreate(
                territory_id=target.id,
                source_territory_id=source.id,
                squad_member_ids=squad_ids,
                warlord_user_id=squad_ids[0],
                expected_rule_version=1,
            ),
            leader,
        )

    db.refresh(clan)
    assert clan.next_attack_at is None


def test_war_power_modifier_uses_percentages_and_cap():
    rules = default_campaign_rule_values()

    assert apply_war_power_modifier(3, 3, rules) == 3.09
    assert apply_war_power_modifier(1, 11, rules) == 1.11
    assert apply_war_power_modifier(3, 100, rules) == 4.05
