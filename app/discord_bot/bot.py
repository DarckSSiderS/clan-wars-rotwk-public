import asyncio
from datetime import datetime, timezone
import logging

import discord
from discord import app_commands
from discord.ext import tasks

from app.database import SessionLocal
from app.discord_bot.community import (
    RolePanel,
    open_ticket,
    close_ticket,
    voice_update,
    cleanup_community,
)
from app.discord_bot.publishing import (
    GOLD,
    Publisher,
    campaign_embed,
    hall_embed,
    weekly_embed,
    safe,
)
from app.discord_bot.snapshot import snapshot
from app.discord_bot.store import Store
from app.discord_bot.sync import GuildManager
from app.models.discord import DiscordLink
from app.services.discord_link_service import issue_link_code, unlink

log = logging.getLogger(__name__)


class PalantirTree(app_commands.CommandTree):
    async def interaction_check(self, interaction):
        if interaction.guild_id != self.client.config.DISCORD_GUILD_ID:
            await interaction.response.send_message(
                "Команды Палантира работают только на сервере bfmeCW.", ephemeral=True
            )
            return False
        return True


class Palantir(discord.Client):
    def __init__(self, config):
        intents = discord.Intents.none()
        intents.guilds = intents.members = intents.guild_messages = (
            intents.voice_states
        ) = True
        super().__init__(
            intents=intents,
            application_id=config.DISCORD_APPLICATION_ID,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.config = config
        self.store = Store(SessionLocal, config.DISCORD_GUILD_ID)
        self.tree = PalantirTree(self)
        self.tree.on_error = self.command_error
        self.mutation_lock = asyncio.Lock()
        self.community_views = []
        self.register_commands()
        self.cycle.change_interval(seconds=config.DISCORD_SYNC_SECONDS)

    def manager(self):
        guild = self.get_guild(self.config.DISCORD_GUILD_ID)
        if guild is None:
            raise ValueError(
                "Бот не видит настроенный сервер. Проверьте DISCORD_GUILD_ID и приглашение."
            )
        return GuildManager(guild, self.store)

    def publisher(self):
        return Publisher(self.manager(), self.store, self.config.DISCORD_SITE_URL)

    async def data(self):
        def read():
            with SessionLocal() as db:
                return snapshot(db)

        return await asyncio.to_thread(read)

    async def setup_hook(self):
        # discord.py views must be created inside the running client loop.
        # The CLI constructs Palantir before Client.run creates that loop.
        self.community_views = [RolePanel(self)]
        for view in self.community_views:
            self.add_view(view)
        guild = discord.Object(id=self.config.DISCORD_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.cycle.start()

    async def close(self):
        self.cycle.cancel()
        await super().close()

    async def on_ready(self):
        log.info("Palantir ready; persistent panels: %s", len(self.persistent_views))

    async def on_interaction(self, interaction):
        if interaction.type == discord.InteractionType.component:
            log.info(
                "Component received: %s; interaction=%s; age=%.3fs",
                (interaction.data or {}).get("custom_id"),
                interaction.id,
                (discord.utils.utcnow() - interaction.created_at).total_seconds(),
            )

    async def command_error(self, interaction, error):
        original = getattr(error, "original", error)
        if isinstance(original, (ValueError, app_commands.CheckFailure)):
            message = str(original)
        elif isinstance(original, discord.Forbidden):
            message = "Недостаточно прав у Палантира. Проверьте права каналов и положение роли бота."
        else:
            log.error(
                "Palantir action failed",
                exc_info=(type(original), original, original.__traceback__),
            )
            message = "Не удалось выполнить действие. Попробуйте позже; подробности есть в журнале бота."
        if interaction.response.is_done():
            await interaction.followup.send(message[:1800], ephemeral=True)
        else:
            await interaction.response.send_message(message[:1800], ephemeral=True)

    @tasks.loop(seconds=60)
    async def cycle(self):
        try:
            async with self.mutation_lock:
                if not self.store.get("setup_complete"):
                    return
                manager = self.manager()
                # Require a complete member cache before revoking/reconciling access.
                if not manager.guild.chunked:
                    await manager.guild.chunk(cache=True)
                data = await self.data()
                await manager.sync_clans(data["clans"], data["identities"])
                await self.publisher().tick(data)
                await cleanup_community(self)
                now = datetime.now(timezone.utc)
                self.store.put("last_success", now.isoformat())
                status = discord.Embed(
                    title="Палантир на страже",
                    colour=GOLD,
                    description=f"Синхронизация: <t:{int(now.timestamp())}:R>\nКланов: {len(data['clans'])}",
                )
                await self.publisher().card("status", "status", status)
        except Exception:
            log.exception("Palantir sync failed; next cycle will retry")

    @cycle.before_loop
    async def before_cycle(self):
        await self.wait_until_ready()

    async def on_member_join(self, member):
        if member.guild.id != self.config.DISCORD_GUILD_ID:
            return
        channel = self.manager().channel("welcome")
        if channel:
            await channel.send(
                f"🌿 **Добро пожаловать в Средиземье, {member.mention}!**",
                embed=self.welcome_embed(),
                allowed_mentions=discord.AllowedMentions(users=[member]),
            )

    async def on_message(self, message):
        if (
            message.author.bot
            or message.guild is None
            or message.guild.id != self.config.DISCORD_GUILD_ID
            or message.type not in {discord.MessageType.default, discord.MessageType.reply}
        ):
            return
        manager = self.manager()
        if message.channel not in [manager.channel("news"), manager.channel("updates")]:
            return
        try:
            async with self.mutation_lock:
                key = f"announcement:{message.id}:everyone"
                if not self.store.sent(key):
                    if not message.mention_everyone:
                        await message.reply(
                            "📯 @everyone — новые вести Средиземья! Обратите внимание на публикацию выше.",
                            mention_author=False,
                            allowed_mentions=discord.AllowedMentions(
                                everyone=True, users=False, roles=False
                            ),
                        )
                    self.store.mark(key)
        except discord.HTTPException:
            log.exception("Could not notify everyone about announcement %s", message.id)
        try:
            if message.thread is None:
                await message.create_thread(
                    name=f"Обсуждение · {message.created_at:%d.%m.%Y}",
                    auto_archive_duration=1440,
                )
        except discord.HTTPException:
            log.exception("Could not open announcement thread")

    async def on_voice_state_update(self, member, before, after):
        async with self.mutation_lock:
            await voice_update(self, member, before, after)

    def welcome_embed(self):
        rules_id = self.store.get("channel:rules")
        roles_id = self.store.get("channel:roles")
        rules = f"<#{rules_id}>" if rules_id else "#правила"
        roles = f"<#{roles_id}>" if roles_id else "#роли-и-привязка"
        return discord.Embed(
            title="🌿 У врат Средиземья · bfmeCW",
            description=(
                "Из тихих земель Шира до крепостей Гондора разносится весть о твоём прибытии. "
                "У нашего костра найдётся место и страннику, и закалённому воину.\n\n"
                "Здесь кланы сражаются за земли Средиземья в Rise of the Witch-king — "
                "Ennorath и Patch 2.02.\n\n"
                f"📜 Загляни в {rules}, прежде чем отправиться в путь.\n"
                f"⚔️ В {roles} выбери свой патч и нужные уведомления.\n"
                f"🔗 Введи `/link` и подтверди код в [настройках профиля]({self.config.DISCORD_SITE_URL}/profile?tab=settings). "
                "Если ты состоишь в клане на сайте, Палантир выдаст его роль и откроет двери штаба в течение минуты.\n\n"
                "*Пусть дорога приведёт тебя к верным спутникам и славным свершениям!*"
            ),
            colour=GOLD,
            url=self.config.DISCORD_SITE_URL,
        )

    async def initial_panels(self):
        publisher = self.publisher()
        await publisher.card(
            "welcome",
            "welcome",
            self.welcome_embed(),
        )
        await publisher.card(
            "rules",
            "rules",
            discord.Embed(
                title="Правила сообщества",
                colour=GOLD,
                description="Уважайте игроков. Без оскорблений, спама и публикации чужих личных данных.\nИгровые споры обсуждайте по существу; обращение к хранителям — /ticket.\nПравила кампании и решения по войнам доступны на сайте.",
                url=self.config.DISCORD_SITE_URL,
            ),
        )
        await publisher.card(
            "roles",
            "roles",
            discord.Embed(
                title="🧭 Выбери свой путь, путник",
                colour=GOLD,
                description=(
                    "Прежде чем покинуть уютный очаг и отправиться навстречу приключениям, выбери свои знамёна.\n\n"
                    "⚔️ **Ennorath / Patch 2.02** — отметь, во что играешь. Можно выбрать оба патча.\n"
                    "📜 **Новости** — подпишись на вести Средиземья.\n"
                    "🔥 **Маяки Гондора** — получай упоминания в штабе своего клана за 6 часов и за 1 час до окончания битвы. "
                    "Эта подписка не даёт дополнительных прав.\n\n"
                    "Кнопки патчей и уведомлений добавляют роль; повторное нажатие снимет её.\n\n"
                    "🔗 **Привязать клан:** нажми синюю кнопку ниже, получи личный одноразовый код и подтверди его "
                    f"в [настройках профиля]({self.config.DISCORD_SITE_URL}/profile?tab=settings). "
                    "Клановая роль и доступ к штабу обновятся в течение минуты."
                ),
            ),
            view=self.community_views[0],
        )

    def register_commands(self):
        @self.tree.command(
            name="setup",
            description="Создать каналы и роли Палантира без удаления существующих",
        )
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.checks.has_permissions(manage_guild=True)
        async def setup(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            async with self.mutation_lock:
                await self.manager().setup()
                await self.initial_panels()
                data = await self.data()
                await self.manager().sync_clans(data["clans"], data["identities"])
                await self.publisher().tick(data)
            await interaction.followup.send(
                "Структура готова. Назначьте доверенным модераторам роль «Хранитель» и проверьте каналы.",
                ephemeral=True,
            )

        @self.tree.command(
            name="link",
            description="Получить одноразовый код для привязки аккаунта сайта",
        )
        @app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)
        async def link(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)

            def issue():
                with SessionLocal() as db:
                    return issue_link_code(db, interaction.user.id)

            code = await asyncio.to_thread(issue)
            await interaction.followup.send(
                "🔮 **Палантир ждёт твоего знака, путник.**\n"
                f"Твой одноразовый код (действует 10 минут):\n`{code}`\n\n"
                f"Открой {self.config.DISCORD_SITE_URL}/profile?tab=settings → Настройки → Discord и вставь код.\n"
                "После подтверждения Палантир узнает твой клан: роль и доступ к штабу обновятся в течение минуты.\n"
                "Код предназначен только для твоего профиля — не передавай его другим.",
                ephemeral=True,
            )

        @self.tree.command(
            name="unlink", description="Отключить свой Discord от аккаунта сайта"
        )
        async def unlink_command(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            async with self.mutation_lock:

                def remove():
                    with SessionLocal() as db:
                        link = (
                            db.query(DiscordLink)
                            .filter_by(discord_user_id=str(interaction.user.id))
                            .first()
                        )
                        if link:
                            unlink(db, link.user_id)

                await asyncio.to_thread(remove)
                data = await self.data()
                await self.manager().sync_clans(data["clans"], data["identities"])
            await interaction.followup.send(
                "Привязка отключена, клановые роли сняты.", ephemeral=True
            )

        @self.tree.command(
            name="campaign", description="Текущие войны и состояние кампании"
        )
        async def campaign(interaction: discord.Interaction):
            await interaction.response.defer()
            await interaction.followup.send(
                embed=campaign_embed(await self.data(), self.config.DISCORD_SITE_URL)
            )

        @self.tree.command(name="clans", description="Кланы, в которые можно вступить")
        async def clans(interaction: discord.Interaction):
            await interaction.response.defer()
            data = await self.data()
            text = "\n".join(
                f"[{safe(c['name'], 100)}]({self.config.DISCORD_SITE_URL}/clans/{c['id']}) · {c['members']}/{c['capacity']}"
                for c in data["clans"]
                if c["recruiting"]
            )
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Набор в кланы",
                    description=text[:4000] or "Открытого набора пока нет.",
                    colour=GOLD,
                )
            )

        @self.tree.command(
            name="weekly", description="Хроника завершённых войн за неделю"
        )
        async def weekly(interaction: discord.Interaction):
            await interaction.response.defer()
            await interaction.followup.send(
                embed=weekly_embed(await self.data(), self.config.DISCORD_SITE_URL)
            )

        @self.tree.command(name="hall", description="Победители завершённых сезонов")
        async def hall(interaction: discord.Interaction):
            await interaction.response.defer()
            await interaction.followup.send(
                embed=hall_embed(await self.data(), self.config.DISCORD_SITE_URL)
            )

        @self.tree.command(
            name="ticket", description="Приватное обращение к хранителям сервера"
        )
        @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
        async def ticket(
            interaction: discord.Interaction, subject: app_commands.Range[str, 3, 300]
        ):
            await interaction.response.defer(ephemeral=True)
            async with self.mutation_lock:
                channel = await open_ticket(self, interaction, subject)
            await interaction.followup.send(
                f"Ваше обращение: {channel.mention}", ephemeral=True
            )

        @self.tree.command(
            name="close-ticket",
            description="Закрыть текущее обращение, сохранив его для хранителей",
        )
        async def close_ticket_command(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            async with self.mutation_lock:
                await close_ticket(self, interaction)
            await interaction.followup.send(
                "Обращение закрыто. Переписка сохранена для хранителей.", ephemeral=True
            )
