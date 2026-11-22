from datetime import timedelta

from app.core.time import utc_now
from app.models.campaign import CampaignSeason, CampaignSeasonClanResult
from app.models.clan import Clan
from app.models.operation import ResourceLedgerEntry
from app.models.territory import Territory
from app.models.war import ClanWar
from app.services.campaign_history_service import CampaignHistoryService
from app.services.clan_economy_service import ClanEconomyService


def _territory(name, owner_id):
    return Territory(
        name=name,
        region="test",
        description="Тестовая территория",
        svg_path_data=f"M {name}",
        owner_clan_id=owner_id,
        influence_value=50,
        required_influence=30,
    )


def test_season_rollover_preserves_rankings_and_starts_new_season(db):
    now = utc_now()
    first = Clan(
        name="Первый клан",
        base_influence=100,
        territory_points=500,
        gold=700,
        iron=20,
        wood=30,
        food=10,
        mithril=3,
    )
    second = Clan(
        name="Второй клан",
        base_influence=100,
        territory_points=350,
        gold=400,
        iron=10,
        wood=15,
        food=8,
        mithril=1,
    )
    db.add_all([first, second])
    db.flush()
    territory = _territory("Тестовый край", first.id)
    db.add(territory)
    db.flush()

    history = CampaignHistoryService()
    old_season = history.create_season(
        db,
        starting_influence=100,
        reset_development=True,
        actor_user_id=None,
        name="Пробный сезон",
        starts_at=now - timedelta(days=7),
    )
    db.add(
        ClanWar(
            territory_id=territory.id,
            attacking_clan_id=first.id,
            defending_clan_id=second.id,
            winner_clan_id=first.id,
            war_type="territory_attack",
            status="completed",
            started_at=now - timedelta(days=3),
            ended_at=now - timedelta(days=1),
        )
    )
    db.commit()

    result = ClanEconomyService().start_new_season(
        db,
        120,
        True,
        season_name="Первый официальный сезон",
    )

    db.refresh(old_season)
    archived = (
        db.query(CampaignSeasonClanResult)
        .filter(CampaignSeasonClanResult.season_id == old_season.id)
        .order_by(CampaignSeasonClanResult.rank)
        .all()
    )
    active = db.query(CampaignSeason).filter(CampaignSeason.status == "active").one()

    assert old_season.status == "completed"
    assert [item.clan_name for item in archived] == ["Первый клан", "Второй клан"]
    assert archived[0].influence == 500
    assert archived[0].wars_won == 1
    assert archived[0].territory_count == 1
    assert active.name == "Первый официальный сезон"
    assert result["completed_season_id"] == old_season.id
    assert territory.owner_clan_id is None
    assert first.territory_points == 120
    assert (first.gold, first.iron, first.wood, first.food, first.mithril) == (
        100,
        6,
        6,
        3,
        0,
    )
    season_entries = (
        db.query(ResourceLedgerEntry)
        .filter_by(clan_id=first.id, action="season_started")
        .all()
    )
    assert {entry.resource for entry in season_entries} == {
        "influence",
        "gold",
        "iron",
        "wood",
        "food",
        "mithril",
    }


def test_influence_history_returns_human_readable_events(db):
    clan = Clan(name="Летописцы", base_influence=100, territory_points=145)
    db.add(clan)
    db.flush()
    db.add(
        ResourceLedgerEntry(
            operation_id="history-test",
            clan_id=clan.id,
            resource="influence",
            amount=45,
            balance_before=100,
            balance_after=145,
            action="territory_influence_gained",
            source_type="territory",
            source_id="1",
            details={"territory_name": "Северный тракт"},
        )
    )
    db.commit()

    result = CampaignHistoryService().influence_history(db, clan_id=clan.id)

    assert result["clans"][0]["territory_influence"] == 45
    assert result["events"][0]["action_label"] == "Получено влияние территории"
    assert result["events"][0]["territory_name"] == "Северный тракт"
