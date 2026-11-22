import pytest
from fastapi import HTTPException

from app.api.v1.territories import add_defending_clan, get_all_territories
from app.models.clan import Clan
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar
from app.services.war_service import ClanWarService


def test_reconcile_territory_war_sides_removes_stale_neutral_defender(db):
    attacker = Clan(name="Атакующий")
    stale_defender = Clan(name="Ложный защитник")
    territory = Territory(
        name="Нейтральная цель",
        region="test",
        description="Тестовая территория",
        svg_path_data="M 0 0",
        status="contested",
    )
    db.add_all([attacker, stale_defender, territory])
    db.flush()

    war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=attacker.id,
        defending_clan_id=None,
        war_type="neutral_capture",
        status="active",
    )
    db.add(war)
    territory.attacking_clans.append(attacker)
    territory.defending_clans.append(stale_defender)
    db.commit()

    repaired = ClanWarService().reconcile_territory_war_sides(db)

    db.refresh(territory)
    assert repaired == 1
    assert [clan.id for clan in territory.attacking_clans] == [attacker.id]
    assert territory.defending_clans == []
    assert territory.status == "contested"
    assert war.defending_clan_id is None


def test_public_territory_list_restores_the_canonical_war_defender(db):
    attacker = Clan(name="Канонический атакующий")
    defender = Clan(name="Канонический защитник")
    stale_defender = Clan(name="Устаревший защитник")
    territory = Territory(
        name="Спорная цель",
        region="test",
        description="Тестовая территория",
        svg_path_data="M 1 1",
        status="contested",
    )
    db.add_all([attacker, defender, stale_defender, territory])
    db.flush()
    db.add(
        ClanWar(
            territory_id=territory.id,
            attacking_clan_id=attacker.id,
            defending_clan_id=defender.id,
            war_type="territory_attack",
            status="active",
        )
    )
    territory.attacking_clans.append(attacker)
    territory.defending_clans.append(stale_defender)
    db.commit()

    get_all_territories(db)

    db.refresh(territory)
    assert [clan.id for clan in territory.attacking_clans] == [attacker.id]
    assert [clan.id for clan in territory.defending_clans] == [defender.id]


def test_admin_cannot_add_a_map_defender_outside_the_active_war(db):
    attacker = Clan(name="Атакующая сторона")
    unrelated_clan = Clan(name="Посторонняя защита")
    territory = Territory(
        name="Нейтральная война",
        region="test",
        description="Тестовая территория",
        svg_path_data="M 2 2",
        status="contested",
    )
    admin = User(username="projection-admin", email="projection-admin@test", hashed_password="x")
    db.add_all([attacker, unrelated_clan, territory, admin])
    db.flush()
    db.add(
        ClanWar(
            territory_id=territory.id,
            attacking_clan_id=attacker.id,
            defending_clan_id=None,
            war_type="neutral_capture",
            status="active",
        )
    )
    db.commit()

    with pytest.raises(HTTPException) as error:
        add_defending_clan(territory.id, unrelated_clan.id, admin, db)

    assert error.value.status_code == 409
    assert territory.defending_clans == []
