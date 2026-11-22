from types import SimpleNamespace
import pytest
import discord

from app.discord_bot.store import Store
from app.discord_bot.sync import GuildManager


class FakeRole:
    def __init__(self, guild, name, **kwargs):
        self.guild, self.name = guild, name
        self.id = guild.next_id()
        self.colour = kwargs.get("colour", discord.Colour.default())
        self.mentionable = kwargs.get("mentionable", False)
        self.hoist = kwargs.get("hoist", False)
        self.position = self.id

    async def edit(self, **kwargs):
        self.__dict__.update({k: v for k, v in kwargs.items() if k != "reason"})
        return self

    def is_assignable(self):
        return True


class FakeChannel:
    def __init__(self, guild, name, **kwargs):
        self.id = guild.next_id()
        self.name, self.guild = name, guild
        self.messages, self.members = [], []
        self.__dict__.update(kwargs)

    async def edit(self, **kwargs):
        self.__dict__.update(kwargs)
        return self

    async def send(self, content=None, **kwargs):
        self.messages.append({"content": content, **kwargs})

    async def delete(self, **kwargs):
        self.guild.channels.remove(self)


class FakeMember:
    def __init__(self, uid, roles):
        self.id, self.roles, self.actions = uid, roles, []

    async def remove_roles(self, *roles, **kwargs):
        self.actions.append(("remove", [r.id for r in roles]))
        self.roles = [r for r in self.roles if r not in roles]

    async def add_roles(self, *roles, **kwargs):
        self.actions.append(("add", [r.id for r in roles]))
        self.roles.extend(r for r in roles if r not in self.roles)

    async def move_to(self, channel, **kwargs):
        self.voice.channel = channel


class FakeGuild:
    def __init__(self):
        self.id, self.counter = 123, 10
        self.roles, self.channels, self.members = [], [], []
        self.default_role = FakeRole(self, "@everyone")
        self.me = SimpleNamespace(id=999)
        # Permission overwrite targets must be hashable, like real Members.
        self.me = FakeMember(999, [])

    def next_id(self):
        self.counter += 1
        return self.counter

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == rid), None)

    def get_channel(self, cid):
        return next((c for c in self.channels if c.id == cid), None)

    async def create_role(self, **kwargs):
        role = FakeRole(self, **kwargs)
        self.roles.append(role)
        return role

    async def create_category(self, name, **kwargs):
        return await self.create_text_channel(name, **kwargs)

    async def create_text_channel(self, name, **kwargs):
        channel = FakeChannel(self, name, **kwargs)
        self.channels.append(channel)
        return channel

    async def create_voice_channel(self, name, **kwargs):
        return await self.create_text_channel(name, **kwargs)


def clan(cid, name):
    return {"id": cid, "name": name, "color": "#123456"}


@pytest.mark.asyncio
async def test_setup_is_repeatable_and_clan_headquarters_are_private(db):
    guild = FakeGuild()
    manager = GuildManager(guild, Store(lambda: db, guild.id, close_sessions=False))
    await manager.setup()
    await manager.sync_clans([clan(1, "Гондор")], {})
    before = ([r.id for r in guild.roles], [c.id for c in guild.channels])
    await manager.setup()
    await manager.sync_clans([clan(1, "Гондор")], {})
    assert before == ([r.id for r in guild.roles], [c.id for c in guild.channels])
    ideas = manager.channel("ideas")
    assert ideas.overwrites[guild.default_role].send_messages is False
    assert ideas.overwrites[guild.default_role].create_public_threads is True
    assert ideas.overwrites[guild.default_role].send_messages_in_threads is True
    assert ideas.overwrites[manager.role("staff")].send_messages is False
    room = manager.channel("clan:1:chat")
    assert room.overwrites[guild.default_role].view_channel is False
    assert room.overwrites[manager.role("clan:1")].view_channel is True
    assert (
        manager.channel("clan:1:orders")
        .overwrites[manager.role("clan:1")]
        .send_messages
        is False
    )


@pytest.mark.asyncio
async def test_transfer_revokes_old_role_before_grant_and_preserves_other_roles(db):
    guild = FakeGuild()
    manager = GuildManager(guild, Store(lambda: db, guild.id, close_sessions=False))
    await manager.setup()
    await manager.sync_clans([clan(1, "A"), clan(2, "B")], {})
    other = await guild.create_role(name="Другая роль")
    member = FakeMember(100, [other, manager.role("clan:1"), manager.role("leader:1")])
    guild.members.append(member)
    await manager.sync_clans(
        [clan(1, "A"), clan(2, "B")], {"100": {"clan_id": 2, "leader": False}}
    )
    assert member.roles == [other, manager.role("clan:2")]
    assert member.actions[0][0] == "remove"
    assert any(
        "100" in (msg["content"] or "")
        for msg in manager.channel("moderation").messages
    )
    await manager.sync_clans([], {})
    assert member.roles == [other]


def test_store_persists_resources_and_delivery_across_instances(db):
    store = Store(lambda: db, 123, close_sessions=False)
    store.put("channel:news", 555)
    store.mark("war:12:completed")
    restarted = Store(lambda: db, 123, close_sessions=False)
    assert restarted.get("channel:news") == 555
    assert restarted.sent("war:12:completed")
    assert not Store(lambda: db, 456, close_sessions=False).sent("war:12:completed")


@pytest.mark.asyncio
async def test_voice_revocation_retries_even_after_role_removal(db):
    guild = FakeGuild()
    manager = GuildManager(guild, Store(lambda: db, 123, close_sessions=False))
    await manager.setup()
    await manager.sync_clans([clan(1, "A")], {})
    member = FakeMember(100, [])
    member.voice = SimpleNamespace(channel=manager.channel("clan:1:voice"))
    guild.members = [member]
    await manager.sync_clans([clan(1, "A")], {})
    assert member.voice.channel is None


@pytest.mark.asyncio
async def test_one_failed_role_revoke_does_not_prevent_other_revocations(db):
    guild = FakeGuild()
    manager = GuildManager(guild, Store(lambda: db, 123, close_sessions=False))
    await manager.setup()
    await manager.sync_clans([clan(1, "A")], {})
    failed = FakeMember(100, [manager.role("clan:1")])
    other = FakeMember(200, [manager.role("clan:1")])

    async def forbidden(*args, **kwargs):
        raise PermissionError("role too high")

    failed.remove_roles = forbidden
    guild.members = [failed, other]
    with pytest.raises(RuntimeError):
        await manager.sync_clans([], {})
    assert other.roles == []


@pytest.mark.asyncio
async def test_opt_in_notifications_can_ping_without_everyone_permission(db):
    guild = FakeGuild()
    manager = GuildManager(guild, Store(lambda: db, 123, close_sessions=False))
    await manager.setup()
    assert manager.role("beacons").mentionable is True
    assert manager.role("news").mentionable is True
    assert manager.role("staff").mentionable is False
