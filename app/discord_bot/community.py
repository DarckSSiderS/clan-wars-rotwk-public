import logging
import discord
from app.discord_bot.publishing import GOLD, safe

log = logging.getLogger(__name__)


class GuildView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    async def interaction_check(self, interaction):
        if interaction.guild_id != self.bot.config.DISCORD_GUILD_ID:
            await interaction.response.send_message(
                "Эта панель доступна на сервере bfmeCW.", ephemeral=True
            )
            return False
        return True

    async def on_error(self, interaction, error, item):
        log.error(
            "Panel failed: %s; interaction=%s",
            getattr(item, "custom_id", None),
            interaction.id,
            exc_info=(type(error), error, error.__traceback__),
        )
        await self.bot.command_error(interaction, error)


class RolePanel(GuildView):
    @discord.ui.button(label="Привязать клан", style=discord.ButtonStyle.primary,
                       custom_id="palantir:link", row=1)
    async def link_clan(self, interaction, button):
        command = self.bot.tree.get_command("link")
        # Reuse /link checks, including its per-user cooldown.
        if await command._check_can_run(interaction):
            await command.callback(interaction)

    async def toggle(self, interaction, key):
        await interaction.response.defer(ephemeral=True, thinking=True)
        log.info("Role click acknowledged: %s; interaction=%s", key, interaction.id)
        async with self.bot.mutation_lock:
            role = self.bot.manager().role(key)
            if role is None:
                await interaction.followup.send(
                    "Сначала администратор должен выполнить /setup.", ephemeral=True
                )
                return
            member = await interaction.guild.fetch_member(interaction.user.id)
            if role in member.roles:
                await member.remove_roles(role, reason="Палантир: выбор участника")
                text = f"🌿 Твой путь изменился: роль «{role.name}» снята. Вернуть её можно этой же кнопкой."
            else:
                await member.add_roles(role, reason="Палантир: выбор участника")
                text = f"✨ Твой выбор записан в летопись: роль «{role.name}» добавлена. Доброго пути!"
            await interaction.followup.send(text, ephemeral=True)
            log.info("Role click completed: %s; interaction=%s", key, interaction.id)

    @discord.ui.button(label="Ennorath", custom_id="palantir:role:ennorath")
    async def ennorath(self, interaction, button):
        await self.toggle(interaction, "ennorath")

    @discord.ui.button(label="Patch 2.02", custom_id="palantir:role:patch202")
    async def patch202(self, interaction, button):
        await self.toggle(interaction, "patch202")

    @discord.ui.button(label="Новости", custom_id="palantir:role:news")
    async def news(self, interaction, button):
        await self.toggle(interaction, "news")

    @discord.ui.button(label="Маяки Гондора", custom_id="palantir:role:beacons")
    async def beacons(self, interaction, button):
        await self.toggle(interaction, "beacons")


async def open_ticket(bot, interaction, subject):
    manager = bot.manager()
    key = f"ticket:{interaction.user.id}"
    old = bot.store.get(key)
    if (
        old
        and not old.get("closed")
        and interaction.guild.get_channel(old["channel_id"])
    ):
        return interaction.guild.get_channel(old["channel_id"])
    category = manager.channel("category:staff")
    if category is None:
        raise ValueError("Сначала администратор должен выполнить /setup.")
    overwrites = manager.permissions("staff")
    overwrites[interaction.user] = discord.PermissionOverwrite(
        view_channel=True,
        send_messages=True,
        read_message_history=True,
        attach_files=True,
    )
    channel = await interaction.guild.create_text_channel(
        f"обращение-{interaction.user.id}",
        category=category,
        overwrites=overwrites,
        topic=f"Палантир: обращение {interaction.user.id}",
    )
    bot.store.put(
        key, {"channel_id": channel.id, "user_id": interaction.user.id, "closed": False}
    )
    await channel.send(
        embed=discord.Embed(
            title="Обращение к хранителям", description=safe(subject, 1000), colour=GOLD
        ),
        allowed_mentions=discord.AllowedMentions.none(),
    )
    return channel


async def close_ticket(bot, interaction):
    tickets = bot.store.items("ticket:")
    record = next(
        (
            (key, val)
            for key, val in tickets.items()
            if val["channel_id"] == interaction.channel_id
        ),
        None,
    )
    if not record:
        raise ValueError("Эта команда работает внутри обращения.")
    key, state = record
    staff = bot.manager().role("staff")
    if (
        interaction.user.id != state["user_id"]
        and not interaction.user.guild_permissions.manage_guild
        and staff not in interaction.user.roles
    ):
        raise ValueError("Закрыть обращение может автор или хранитель.")
    await interaction.channel.edit(
        overwrites=bot.manager().permissions("staff"),
        name=f"закрыто-{state['user_id']}",
    )
    bot.store.put(key, {**state, "closed": True})


async def voice_update(bot, member, before, after):
    if member.bot or member.guild.id != bot.config.DISCORD_GUILD_ID:
        return
    manager = bot.manager()
    create = manager.channel("voice-create")
    if not create or after.channel != create:
        return
    key = f"temporary_voice:{member.id}"
    existing = member.guild.get_channel(bot.store.get(key, 0))
    if existing is None:
        existing = await member.guild.create_voice_channel(
            f"Отряд · {member.display_name}"[:100],
            category=manager.channel("category:voice"),
            overwrites=manager.permissions("public"),
            user_limit=8,
        )
        bot.store.put(key, existing.id)
    await member.move_to(existing)


async def cleanup_community(bot):
    guild = bot.get_guild(bot.config.DISCORD_GUILD_ID)
    for key, channel_id in bot.store.items("temporary_voice:").items():
        channel = guild.get_channel(channel_id)
        if channel and not channel.members:
            await channel.delete(reason="Палантир: временный отряд опустел")
            bot.store.delete(key)
        elif channel is None:
            bot.store.delete(key)
