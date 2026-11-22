import pytest
import asyncio
from datetime import datetime, timezone
import discord
from unittest.mock import AsyncMock

from app.discord_bot.bot import Palantir
from app.config import Settings
from types import SimpleNamespace
from app.discord_bot.community import open_ticket, close_ticket, cleanup_community
from app.discord_bot.store import Store
from app.discord_bot.sync import GuildManager
from test_discord_guild import FakeGuild, FakeMember


@pytest.mark.asyncio
async def test_announcements_notify_everyone_once_only_in_news_channels(db, monkeypatch):
    bot = Palantir(Settings(DISCORD_ENABLED=True, DISCORD_GUILD_ID=123, _env_file=None))
    bot.store = Store(lambda: db, 123, close_sessions=False)
    news, updates, chat = object(), object(), object()
    monkeypatch.setattr(bot, "manager", lambda: SimpleNamespace(
        channel=lambda key: {"news": news, "updates": updates}.get(key)
    ))
    for index, channel in enumerate((news, updates)):
        message = SimpleNamespace(
            id=100+index, author=SimpleNamespace(bot=False), guild=SimpleNamespace(id=123),
            channel=channel, type=discord.MessageType.default, mention_everyone=False,
            thread=None, created_at=datetime.now(timezone.utc),
            reply=AsyncMock(), create_thread=AsyncMock(),
        )
        await bot.on_message(message)
        await bot.on_message(message)
        message.reply.assert_awaited_once()
        args, kwargs = message.reply.call_args
        assert "@everyone" in args[0]
        assert kwargs["mention_author"] is False
        assert kwargs["allowed_mentions"].everyone is True
        assert kwargs["allowed_mentions"].roles is False
        assert kwargs["allowed_mentions"].users is False
        message.reply.reset_mock()
        message.id += 10
        message.channel = chat
        await bot.on_message(message)
        message.reply.assert_not_awaited()
        message.channel = channel
        message.author.bot = True
        await bot.on_message(message)
        message.reply.assert_not_awaited()
        message.author.bot = False
        message.type = discord.MessageType.pins_add
        await bot.on_message(message)
        message.reply.assert_not_awaited()
    await bot.close()


@pytest.mark.asyncio
async def test_restored_role_button_acknowledges_before_waiting_for_sync(db, monkeypatch):
    config = Settings(DISCORD_ENABLED=True, DISCORD_GUILD_ID=123, _env_file=None)
    # The production CLI constructs the client before Client.run starts its loop.
    bot = await asyncio.to_thread(Palantir, config)
    guild = FakeGuild()
    store = Store(lambda: db, guild.id, close_sessions=False)
    manager = GuildManager(guild, store)
    await manager.setup()
    monkeypatch.setattr(bot, "manager", lambda: manager)
    monkeypatch.setattr(bot.tree, "sync", AsyncMock())
    monkeypatch.setattr(bot.cycle, "start", lambda: None)
    await bot.setup_hook()
    member = FakeMember(100, [])
    guild.fetch_member = AsyncMock(return_value=member)
    acknowledged, completed = asyncio.Event(), asyncio.Event()

    async def defer(**kwargs):
        assert kwargs == {"ephemeral": True, "thinking": True}
        acknowledged.set()

    async def followup(text, **kwargs):
        assert "Ennorath" in text
        completed.set()

    interaction = SimpleNamespace(
        id=123456, guild_id=123, guild=guild, user=member,
        message=SimpleNamespace(id=999999),
        data={"custom_id": "palantir:role:ennorath", "component_type": 2},
        response=SimpleNamespace(defer=defer),
        followup=SimpleNamespace(send=followup),
    )
    await bot.mutation_lock.acquire()
    try:
        bot._connection._view_store.dispatch_view(2, "palantir:role:ennorath", interaction)
        await asyncio.wait_for(acknowledged.wait(), timeout=1)
        guild.fetch_member.assert_not_awaited()
    finally:
        bot.mutation_lock.release()
    await asyncio.wait_for(completed.wait(), timeout=1)
    assert manager.role("ennorath") in member.roles
    await bot.close()


@pytest.mark.asyncio
async def test_real_command_registration_and_persistent_views():
    config = Settings(DISCORD_ENABLED=True, DISCORD_GUILD_ID=123, _env_file=None)
    bot = Palantir(config)
    names = {c.name for c in bot.tree.get_commands()}
    assert {
        "setup",
        "link",
        "unlink",
        "campaign",
        "clans",
        "weekly",
        "hall",
        "ticket",
        "close-ticket",
    } == names
    for command in bot.tree.get_commands():
        command.to_dict(
            bot.tree
        )  # real discord.py serialization catches unsupported annotations
    assert not bot.intents.message_content
    assert bot.intents.members
    assert all(view.is_persistent() for view in bot.community_views)
    await bot.close()


@pytest.mark.asyncio
async def test_ticket_is_private_cannot_be_closed_by_stranger_and_keeps_history(db):
    guild = FakeGuild()
    store = Store(lambda: db, guild.id, close_sessions=False)
    manager = GuildManager(guild, store)
    await manager.setup()
    bot = SimpleNamespace(manager=lambda: manager, store=store)
    author = FakeMember(100, [])
    author.guild_permissions = SimpleNamespace(manage_guild=False)
    interaction = SimpleNamespace(user=author, guild=guild)
    room = await open_ticket(bot, interaction, "Помогите с кланом")
    assert await open_ticket(bot, interaction, "Ещё раз") is room
    assert room.overwrites[guild.default_role].view_channel is False
    assert room.overwrites[author].view_channel is True
    interaction.channel_id, interaction.channel = room.id, room
    stranger = FakeMember(200, [])
    stranger.guild_permissions = SimpleNamespace(manage_guild=False)
    interaction.user = stranger
    with pytest.raises(ValueError):
        await close_ticket(bot, interaction)
    interaction.user = author
    await close_ticket(bot, interaction)
    assert author not in room.overwrites
    assert room in guild.channels
    assert len(room.messages) == 1


@pytest.mark.asyncio
async def test_voice_cleanup_only_deletes_empty_managed_rooms(db):
    guild = FakeGuild()
    store = Store(lambda: db, guild.id, close_sessions=False)
    owned = await guild.create_voice_channel("Temporary")
    unrelated = await guild.create_voice_channel("Not managed")
    occupied = await guild.create_voice_channel("Occupied")
    occupied.members = [FakeMember(200, [])]
    store.put("temporary_voice:100", owned.id)
    store.put("temporary_voice:200", occupied.id)
    bot = SimpleNamespace(
        store=store,
        get_guild=lambda uid: guild,
        config=SimpleNamespace(DISCORD_GUILD_ID=guild.id),
    )
    await cleanup_community(bot)
    assert owned not in guild.channels
    assert unrelated in guild.channels
    assert occupied in guild.channels
