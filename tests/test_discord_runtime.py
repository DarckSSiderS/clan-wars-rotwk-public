from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
import discord

from app.discord_bot.store import Store
from app.discord_bot.snapshot import snapshot
from app.discord_bot.publishing import Publisher, campaign_embed, pending_events, war_embed
from app.models.clan import Clan, ClanMember
from app.models.discord import DiscordLink
from app.models.user import User

NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)


def data(status="active", remaining=5):
    return {
        "paused": False,
        "season": "Осень",
        "clans": [],
        "hall": [],
        "identities": {},
        "wars": [
            {
                "id": 1,
                "status": status,
                "territory": "Минас Тирит",
                "attacker_id": 1,
                "defender_id": 2,
                "attacker": "Гондор",
                "defender": "Мордор",
                "winner": "Гондор",
                "attacker_score": 20,
                "defender_score": 10,
                "started_at": (NOW - timedelta(hours=50)).isoformat(),
                "ends_at": (NOW + timedelta(hours=remaining)).isoformat(),
                "ended_at": NOW.isoformat() if status != "active" else None,
            }
        ],
    }


def test_empty_campaign_and_long_names_stay_inside_embed_limits():
    record = data()
    record["season"] = "X" * 6000
    record["clans"] = [
        {"id": i, "name": "Y" * 6000, "territories": 1, "influence": 100}
        for i in range(40)
    ]
    embed = campaign_embed(record, "https://bfmecw.online")
    assert len(embed) <= 6000
    assert len(embed.title) <= 256
    assert all(len(f.value) <= 1024 for f in embed.fields)
    assert (
        "Нет"
        in campaign_embed(
            {"clans": [], "wars": [], "paused": False, "season": None},
            "https://bfmecw.online",
        ).description
    )


def test_reminders_do_not_fire_when_paused_or_expired():
    record = data(remaining=0.5)
    reminders = [e for e in pending_events(record, NOW) if e[0].startswith("beacon:")]
    assert len(reminders) == 2  # one for each clan, only the most urgent threshold
    record["paused"] = True
    assert not any(e[0].startswith("beacon:") for e in pending_events(record, NOW))
    assert not any(
        e[0].startswith("beacon:") for e in pending_events(data(remaining=-1), NOW)
    )


def test_campaign_identifies_sides_scores_and_links_each_battle():
    record = data()
    embed = campaign_embed(record, "https://bfmecw.online")
    battle = embed.fields[0]
    assert "Минас Тирит" in battle.name
    assert "Атакует: **Гондор**" in battle.value
    assert "Защищает: **Мордор**" in battle.value
    assert "Очки атаки: **20.0**" in battle.value
    assert "очки защиты: **10.0**" in battle.value
    assert "https://bfmecw.online/battles/1" in battle.value
    event = war_embed(record["wars"][0], "https://bfmecw.online")
    assert "Атакует: **Гондор**" in event.description
    assert event.url == "https://bfmecw.online/battles/1"


def test_neutral_capture_does_not_invent_a_defending_clan_or_score():
    record = data()
    record["wars"][0]["defender_id"] = None
    record["wars"][0]["defender"] = "Нейтральная земля"
    record["paused"] = True
    battle = campaign_embed(record, "https://bfmecw.online").fields[0].value
    assert "Захват нейтральной территории" in battle
    assert "Защищает:" not in battle
    assert "очки защиты:" not in battle
    assert "Таймер приостановлен" in battle
    assert "<t:" not in battle


def test_cycle_snapshot_exposes_schedule_not_hidden_orders(db):
    from app.services.campaign_cycle_store import CampaignCycleStore
    from tests.test_cycle_plan_service import setup_world

    _, _, _, cycle = setup_world(db)
    deadline = CampaignCycleStore.timeline(cycle).replay_deadline
    cycle.settled_at = deadline
    db.flush()
    result = snapshot(db, now=deadline + timedelta(hours=1))["cycle"]
    assert result["phase"] == "rest"
    assert datetime.fromisoformat(result["next_cycle_starts_at"]) == deadline + timedelta(hours=12)
    assert "orders" not in result and "planning_snapshot" not in result


class Message:
    def __init__(self, mid):
        self.id = mid

    async def edit(self, **kwargs):
        pass


class Channel:
    def __init__(self):
        self.messages, self.fail = [], False

    async def send(self, **kwargs):
        if self.fail:
            raise OSError("network down")
        msg = Message(len(self.messages) + 1)
        self.messages.append((msg, kwargs))
        return msg

    async def fetch_message(self, mid):
        return next(m for m, _ in self.messages if m.id == mid)


@pytest.mark.asyncio
async def test_cycle_schedule_announces_major_transitions_once_and_updates_clan_cards(db):
    keys = ["chat", "campaign", "clan:7:summary"]
    channels = {key: Channel() for key in keys}
    manager = SimpleNamespace(channel=channels.get, role=lambda key: None)
    store = Store(lambda: db, 123, close_sessions=False)
    record = data()
    record["wars"] = []
    record["clans"] = [dict(id=7, name="Гондор", territories=2, influence=10,
                            level=1, members=4, capacity=6, recruiting=False)]
    record["cycle"] = dict(id=42, number=2, phase="preparation", preparation_at=NOW.isoformat(),
                           battle_at=(NOW + timedelta(hours=24)).isoformat(),
                           battle_ends_at=(NOW + timedelta(hours=72)).isoformat(), next_cycle_starts_at=None)
    await Publisher(manager, store, "https://bfmecw.online").tick(record, NOW)
    await Publisher(manager, store, "https://bfmecw.online").tick(record, NOW)
    assert len(channels["chat"].messages) == 1
    notice = channels["chat"].messages[0][1]
    assert "Подготовка" in notice["embed"].title
    assert not notice["allowed_mentions"].everyone
    assert any(field.name == "Начало боёв" for field in channels["campaign"].messages[0][1]["embed"].fields)
    assert "/orders" in channels["clan:7:summary"].messages[0][1]["embed"].fields[0].value
    record["cycle"]["phase"] = "battle"
    await Publisher(manager, store, "https://bfmecw.online").tick(record, NOW)
    assert len(channels["chat"].messages) == 2
    assert len(channels["clan:7:summary"].messages) == 1

@pytest.mark.asyncio
async def test_first_boot_baseline_restart_and_failed_send_retry(db):
    channels = {
        k: Channel() for k in ["campaign", "chronicle", "clan:1:chat", "clan:2:chat"]
    }
    manager = SimpleNamespace(
        channel=lambda key: channels.get(key), role=lambda key: None
    )
    store = Store(lambda: db, 123, close_sessions=False)
    publisher = Publisher(manager, store, "https://bfmecw.online")
    await publisher.tick(data(remaining=20), NOW)
    assert channels["chronicle"].messages == []
    channels["chronicle"].fail = True
    with pytest.raises(OSError):
        await publisher.tick(data(status="completed"), NOW)
    channels["chronicle"].fail = False
    await publisher.tick(data(status="completed"), NOW)
    assert len(channels["chronicle"].messages) == 1
    await Publisher(manager, store, "https://bfmecw.online").tick(
        data(status="completed"), NOW
    )
    assert len(channels["chronicle"].messages) == 1
    assert len(channels["campaign"].messages) == 1


def test_snapshot_omits_inactive_links_and_deleted_or_admin_clans(db):
    member = User(username="frodo", is_active=True, is_claimed=True)
    db.add(member)
    db.flush()
    a = Clan(name="Гондор", leader_id=member.id, is_admin_clan=False, is_deleted=False)
    db.add_all(
        [a, Clan(name="Архив", is_deleted=True), Clan(name="Совет", is_admin_clan=True)]
    )
    db.flush()
    db.add_all(
        [
            ClanMember(user_id=member.id, clan_id=a.id),
            DiscordLink(
                user_id=member.id, discord_user_id="1551937393144238201", created_at=NOW
            ),
        ]
    )
    db.commit()
    result = snapshot(db, NOW)
    assert [c["name"] for c in result["clans"]] == ["Гондор"]
    assert result["identities"]["1551937393144238201"] == {
        "clan_id": a.id,
        "leader": True,
    }
    member.is_active = False
    db.commit()
    assert snapshot(db, NOW)["identities"] == {}


def test_snapshot_uses_canonical_influence_and_adjusted_war_scores(db):
    from app.models.territory import Territory
    from app.models.war import ClanWar, ClanWarParticipant
    from app.models.war_adjustment import WarScoreAdjustment

    member = User(username="aragorn", is_active=True, is_claimed=True)
    db.add(member)
    db.flush()
    clan = Clan(name="Гондор", base_influence=100, territory_points=150)
    territory = Territory(name="Минас Тирит", region="Гондор", svg_path_data="M0 0")
    db.add_all([clan, territory])
    db.flush()
    war = ClanWar(
        territory_id=territory.id,
        attacking_clan_id=clan.id,
        war_type="neutral_capture",
        status="active",
        started_at=NOW,
    )
    db.add(war)
    db.flush()
    db.add(
        ClanWarParticipant(
            war_id=war.id, clan_id=clan.id, user_id=member.id, war_points=10, wins=2
        )
    )
    db.add(
        WarScoreAdjustment(
            war_id=war.id,
            clan_id=clan.id,
            actor_id=member.id,
            request_id="test-discord-adjustment",
            points=5,
            reason="Correction",
        )
    )
    db.commit()
    result = snapshot(db, NOW)
    assert result["clans"][0]["influence"] == 150
    assert result["wars"][0]["attacker_score"] == 15


@pytest.mark.asyncio
async def test_card_reappears_if_message_was_deleted_but_content_unchanged(db):
    channel = Channel()
    manager = SimpleNamespace(channel=lambda key: channel)
    publisher = Publisher(
        manager, Store(lambda: db, 123, close_sessions=False), "https://bfmecw.online"
    )
    embed = discord.Embed(title="Живая карточка")
    await publisher.card("test", "campaign", embed)

    async def missing(mid):
        raise discord.NotFound(
            SimpleNamespace(status=404, reason="Not Found"), "deleted"
        )

    channel.fetch_message = missing
    await publisher.card("test", "campaign", embed)
    assert len(channel.messages) == 2
