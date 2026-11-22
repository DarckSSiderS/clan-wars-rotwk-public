import logging
import discord
from app.discord_bot.layout import LAYOUT, ROLES

log = logging.getLogger(__name__)
REASON = "Палантир: синхронизация bfmeCW"


class GuildManager:
    def __init__(self, guild, store):
        self.guild, self.store = guild, store

    def role(self, key):
        return self.guild.get_role(self.store.get("role:" + key, 0))

    def channel(self, key):
        return self.guild.get_channel(self.store.get("channel:" + key, 0))

    async def audit(self, member_id, action, roles):
        channel = self.channel("moderation")
        if channel is None:
            return
        names = ", ".join(str(role.id) for role in roles)
        try:
            await channel.send(
                f"{action} · Discord ID {member_id} · роли {names}",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            log.exception("Could not write the Discord moderation journal")

    def permissions(self, access="public", clan_role=None, leader_role=None):
        private = access in {"staff", "clan", "orders"}
        result = {
            self.guild.default_role: discord.PermissionOverwrite(
                view_channel=not private,
                send_messages=access == "public",
                send_messages_in_threads=not private,
                create_public_threads=access == "threads",
                read_message_history=True,
                mention_everyone=False,
                connect=not private,
            ),
            self.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True,
                connect=True,
                move_members=True,
                create_public_threads=True,
                send_messages_in_threads=True,
                manage_threads=True,
            ),
        }
        staff = self.role("staff")
        if staff:
            result[staff] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=access != "threads",
                read_message_history=True,
                connect=True,
                create_public_threads=access == "threads",
                send_messages_in_threads=True,
            )
        if clan_role:
            result[clan_role] = discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                connect=True,
                send_messages=access != "orders",
                send_messages_in_threads=access != "orders",
            )
        if leader_role and access == "orders":
            result[leader_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True
            )
        return result

    async def ensure_role(self, key, name, color=0):
        role = self.role(key)
        mentionable = key in {"beacons", "news"}
        hoist = key.startswith("clan:")
        if role is None:
            role = await self.guild.create_role(
                name=name[:100],
                colour=discord.Colour(color),
                permissions=discord.Permissions.none(),
                mentionable=mentionable,
                hoist=hoist,
                reason=REASON,
            )
            self.store.put("role:" + key, role.id)
        elif (
            role.name != name[:100]
            or role.colour.value != color
            or role.mentionable != mentionable
            or role.hoist != hoist
        ):
            role = await role.edit(
                name=name[:100],
                colour=discord.Colour(color),
                mentionable=mentionable,
                hoist=hoist,
                reason=REASON,
            )
        return role

    async def ensure_channel(self, key, name, kind, permissions, category=None):
        channel = self.channel(key)
        if channel:
            # Reassert private boundaries on managed channels; never adopt by display name.
            if channel.overwrites != permissions:
                channel = await channel.edit(overwrites=permissions, reason=REASON)
            return channel
        kwargs = {"overwrites": permissions, "reason": REASON}
        if category:
            kwargs["category"] = category
        if kind == "text":
            kwargs["topic"] = "Палантир · " + key
        create = getattr(
            self.guild,
            {
                "category": "create_category",
                "text": "create_text_channel",
                "voice": "create_voice_channel",
            }[kind],
        )
        channel = await create(name[:100], **kwargs)
        self.store.put("channel:" + key, channel.id)
        return channel

    async def setup(self):
        for key, name in ROLES.items():
            await self.ensure_role(key, name)
        for key, name, children in LAYOUT:
            category = await self.ensure_channel(
                "category:" + key,
                name,
                "category",
                self.permissions("staff" if key == "staff" else "public"),
            )
            for child_key, child_name, kind, access in children:
                await self.ensure_channel(
                    child_key, child_name, kind, self.permissions(access), category
                )
        self.store.put("setup_complete", True)

    async def sync_clans(self, clans, identities):
        # Revoke old access BEFORE provisioning or adding anything. A provisioning
        # failure must never leave a transferred/unlinked member in an old HQ.
        wanted = {}
        active = {c["id"] for c in clans}
        managed = self.store.items("role:clan:") | self.store.items("role:leader:")
        voice_clans = {
            value: key.split(":")[2]
            for key, value in self.store.items("channel:clan:").items()
            if key.endswith(":voice")
        }
        failures = []
        for member in self.guild.members:
            identity = identities.get(str(member.id), {})
            cid = identity.get("clan_id")
            keys = {f"clan:{cid}"} if cid in active else set()
            if keys and identity.get("leader"):
                keys.add(f"leader:{cid}")
            wanted[member.id] = keys
            obsolete = [
                role
                for role in member.roles
                if any(
                    role.id == rid and key[5:] not in keys
                    for key, rid in managed.items()
                )
            ]
            if obsolete:
                try:
                    await member.remove_roles(*obsolete, reason=REASON)
                    await self.audit(member.id, "Снят клановый доступ", obsolete)
                except Exception as exc:
                    failures.append(exc)
                    log.exception(
                        "Could not revoke clan roles for member %s", member.id
                    )
            voice = getattr(getattr(member, "voice", None), "channel", None)
            voice_clan = voice_clans.get(voice.id) if voice else None
            is_staff = self.role("staff") in member.roles or getattr(
                getattr(member, "guild_permissions", None), "administrator", False
            )
            if voice_clan and f"clan:{voice_clan}" not in keys and not is_staff:
                try:
                    await member.move_to(None, reason=REASON)
                except Exception as exc:
                    failures.append(exc)
                    log.exception(
                        "Could not revoke clan voice access for member %s", member.id
                    )
        if failures:
            raise RuntimeError(
                "Не удалось снять часть клановых доступов; выдача новых ролей отложена. Проверьте журнал и иерархию ролей."
            ) from failures[0]
        for clan in clans:
            cid = clan["id"]
            try:
                color = int((clan.get("color") or "#B59A56").lstrip("#"), 16)
                if not 0 <= color <= 0xFFFFFF:
                    color = 0xB59A56
            except ValueError:
                color = 0xB59A56
            role = await self.ensure_role(
                f"clan:{cid}", f"⚑ {clan['name'][:75]} [{cid}]", color
            )
            leader = await self.ensure_role(f"leader:{cid}", f"Глава [{cid}]")
            permissions = self.permissions("clan", role, leader)
            category = await self.ensure_channel(
                f"clan:{cid}:category",
                f"⚑ {clan['name'][:75]} [{cid}]",
                "category",
                permissions,
            )
            for key, name, kind in [
                ("orders", "приказы", "text"),
                ("chat", "чат", "text"),
                ("summary", "сводка", "text"),
                ("voice", "Совет клана", "voice"),
            ]:
                access = "orders" if key in {"orders", "summary"} else "clan"
                perms = self.permissions(
                    access, role, leader if key == "orders" else None
                )
                await self.ensure_channel(
                    f"clan:{cid}:{key}", name, kind, perms, category
                )
        for member in self.guild.members:
            roles = [self.role(key) for key in wanted[member.id]]
            missing = [r for r in roles if r is not None and r not in member.roles]
            if missing:
                if not all(r.is_assignable() for r in missing):
                    raise RuntimeError("Поднимите роль Палантира выше клановых ролей.")
                await member.add_roles(*missing, reason=REASON)
                await self.audit(member.id, "Выдан клановый доступ", missing)
