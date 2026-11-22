from datetime import datetime, timezone
import hashlib
import discord

GOLD = 0xB59A56
PHASE_LABELS = {
    "scheduled": "Ожидается старт",
    "registration": "Стартовый выбор",
    "preparation": "Подготовка к боям",
    "battle": "Бои идут",
    "replay_loading": "Загрузка последних реплеев",
    "settlement": "Подведение итогов",
    "rest": "Итоги подведены, идёт перерыв",
    "complete": "Цикл завершён",
    "season_ended": "Сезон завершён",
}


def cycle_dates(cycle):
    fields = {
        "registration": (("Подготовка", "preparation_at"), ("Начало боёв", "battle_at"), ("Окончание боёв", "battle_ends_at")),
        "preparation": (("Подготовка", "preparation_at"), ("Начало боёв", "battle_at"), ("Окончание боёв", "battle_ends_at")),
        "battle": (("Начало боёв", "battle_at"), ("Окончание боёв", "battle_ends_at")),
        "replay_loading": (("Срок загрузки реплеев", "replay_deadline"),),
    }.get(cycle["phase"], ())
    dates = [(label, f"<t:{int(datetime.fromisoformat(cycle[key]).timestamp())}:F>")
             for label, key in fields if cycle.get(key)]
    following = cycle.get("next_cycle_starts_at")
    if following:
        stamp = int(datetime.fromisoformat(following).timestamp())
        dates.append((f"Начало цикла {cycle['number'] + 1}", f"<t:{stamp}:F> · <t:{stamp}:R>"))
    elif cycle["phase"] == "settlement" and not cycle.get("season_end_requested"):
        dates.append(("Следующий цикл", "Через 12 часов после подведения итогов."))
    return dates


def cycle_action(cycle, site):
    href = f"{site}/campaign/cycles/{cycle['id']}"
    if cycle["phase"] == "preparation":
        return f"[Распределить отряды]({href}/orders) · [Карта]({site}/map)"
    if cycle["phase"] == "registration":
        return f"[Стартовый выбор]({href}/preparation) · [Карта]({site}/map)"
    return f"[Битвы и итоги]({href}) · [Карта]({site}/map)"


def cycle_embed(cycle, site):
    phase = PHASE_LABELS.get(cycle["phase"], "Расписание")
    embed = discord.Embed(title=f"Цикл {cycle['number']} · {phase}", colour=GOLD,
                          url=f"{site}/map", description=cycle_action(cycle, site))
    for label, value in cycle_dates(cycle):
        embed.add_field(name=label, value=value, inline=False)
    return embed


def safe(text, limit=200):
    return discord.utils.escape_markdown(
        discord.utils.escape_mentions(str(text or ""))
    )[:limit]


def battle_details(war, paused=False):
    lines = [f"⚔️ Атакует: **{safe(war['attacker'], 65)}**"]
    if war["defender_id"] is None:
        lines += [
            "🏳️ Захват нейтральной территории — защищающегося клана нет.",
            f"Очки атаки: **{war['attacker_score']:.1f}**",
        ]
    else:
        lines += [
            f"🛡️ Защищает: **{safe(war['defender'], 65)}**",
            f"Очки атаки: **{war['attacker_score']:.1f}** · очки защиты: **{war['defender_score']:.1f}**",
        ]
    if war["status"] == "active":
        if paused:
            lines.append("⏸ Таймер приостановлен.")
        elif war["ends_at"]:
            end = datetime.fromisoformat(war["ends_at"])
            if end <= datetime.now(timezone.utc):
                lines.append("⌛ Время истекло — ожидается подведение итогов.")
            else:
                stamp = int(end.timestamp())
                lines.append(f"⏳ Окончание: <t:{stamp}:R> · <t:{stamp}:f>")
    return "\n".join(lines)


def campaign_embed(data, site):
    active = [w for w in data["wars"] if w["status"] == "active"]
    cycle = data.get("cycle")
    embed = discord.Embed(
        title=("Палантир · " + safe(data.get("season") or "Кампания", 180)),
        description=("⏸ Кампания приостановлена.\n\n" if data["paused"] else "")
        + (cycle_embed(cycle, site).description if cycle
           else "⚔️ **Битвы за территории**" if active else "Нет активных войн."),
        colour=GOLD,
        url=site,
    )
    if cycle:
        embed.add_field(name=f"Цикл {cycle['number']}", value=PHASE_LABELS[cycle["phase"]], inline=False)
        for label, value in cycle_dates(cycle):
            embed.add_field(name=label, value=value)
    for war in active[:8]:
        embed.add_field(
            name=f"📍 {safe(war['territory'], 80)} · №{war['id']}",
            value=battle_details(war, data["paused"])
            + f"\n[Открыть битву →]({site.rstrip('/')}/battles/{war['id']})",
            inline=False,
        )
    if len(active) > 8:
        embed.add_field(
            name="Остальные битвы",
            value=f"Ещё {len(active) - 8} — подробности на [сайте]({site}).",
            inline=False,
        )
    top = "\n".join(
        f"{i}. {safe(c['name'], 65)} · {c['territories']} земель · {c['influence']} влияния"
        for i, c in enumerate(data["clans"][:8], 1)
    )
    embed.add_field(
        name="🏰 Кланы · влияние", value=top[:1024] or "Кланы ещё не созданы.", inline=False
    )
    embed.set_footer(text="Расписание обновляется автоматически" if cycle
                     else f"Активных войн: {len(active)} · подробности на bfmecw.online")
    return embed


def war_embed(war, site, title=None):
    status = {
        "active": "Начало похода",
        "completed": "Итоги войны",
        "canceled": "Поход отменён",
    }.get(war["status"], war["status"])
    text = battle_details(war)
    if war["status"] == "completed":
        text += "\nПобедитель: " + safe(war["winner"])
    return discord.Embed(
        title=f"{title or status} · {safe(war['territory'], 120)}"[:256],
        description=text,
        colour=GOLD,
        url=f"{site.rstrip('/')}/battles/{war['id']}",
    )


def pending_events(data, now):
    events = []
    for war in data["wars"]:
        suffix = war["status"]
        if suffix != "active":
            fingerprint = (
                f"{war['winner']}:{war['attacker_score']}:{war['defender_score']}"
            )
            suffix += ":" + hashlib.sha256(fingerprint.encode()).hexdigest()[:12]
        events.append((f"war:{war['id']}:{suffix}", "chronicle", war, None))
        if war["status"] != "active" or not war["ends_at"] or data["paused"]:
            continue
        end = datetime.fromisoformat(war["ends_at"])
        hours = (end - now).total_seconds() / 3600
        threshold = 1 if 0 < hours <= 1 else 6 if 1 < hours <= 6 else None
        if threshold is None:
            continue
        for cid in {war["attacker_id"], war["defender_id"]} - {None}:
            events.append(
                (
                    f"beacon:{war['id']}:{cid}:{int(end.timestamp())}:{threshold}",
                    f"clan:{cid}:chat",
                    war,
                    f"Маяки Гондора · осталось менее {threshold} ч",
                )
            )
    return events


class Publisher:
    def __init__(self, manager, store, site):
        self.manager, self.store, self.site = manager, store, site.rstrip("/")

    async def card(self, key, channel_key, embed, view=None):
        channel = self.manager.channel(channel_key)
        if channel is None:
            return
        message_id = self.store.get("message:" + key)
        digest = hashlib.sha256(str(embed.to_dict()).encode()).hexdigest()
        if message_id:
            try:
                msg = await channel.fetch_message(message_id)
                if self.store.get("digest:" + key) == digest and view is None:
                    return
                await msg.edit(
                    embed=embed,
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.NotFound:
                message_id = None
        if not message_id:
            msg = await channel.send(
                embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none()
            )
            self.store.put("message:" + key, msg.id)
        self.store.put("digest:" + key, digest)

    async def tick(self, data, now=None):
        now = now or datetime.now(timezone.utc)
        events = pending_events(data, now)
        if not self.store.get("events_initialized"):
            for key, _, _, title in events:
                if title is None:
                    self.store.mark(key)
            self.store.put("events_initialized", True)
        await self.card("campaign", "campaign", campaign_embed(data, self.site))
        cycle = data.get("cycle")
        for clan in data["clans"]:
            text = (
                f"{safe(clan.get('motto'), 160)}\nУровень: {clan['level']} · "
                f"Участников: {clan['members']}/{clan['capacity']}\n"
                f"Земель: {clan['territories']} · Влияние: {clan['influence']}\n"
                + (
                    "Набор открыт — подайте заявку на сайте."
                    if clan["recruiting"]
                    else "Набор закрыт."
                )
            )
            embed = discord.Embed(
                title=safe(clan["name"]),
                description=text,
                colour=GOLD,
                url=f"{self.site}/clans/{clan['id']}",
            )
            await self.card(f"clan:{clan['id']}", "recruitment", embed)
            if cycle:
                schedule = [f"**{label}** · {value}" for label, value in cycle_dates(cycle)]
                embed = discord.Embed.from_dict(embed.to_dict())
                embed.add_field(name=f"Цикл {cycle['number']} · {PHASE_LABELS[cycle['phase']]}",
                                value="\n".join([cycle_action(cycle, self.site), *schedule]), inline=False)
            await self.card(
                f"clan-summary:{clan['id']}", f"clan:{clan['id']}:summary", embed
            )
        if cycle and cycle["phase"] in {"preparation", "battle", "rest"}:
            key = f"campaign-cycle:{cycle['id']}:{cycle['phase']}"
            channel = self.manager.channel("chat")
            if channel and not self.store.sent(key):
                await channel.send(embed=cycle_embed(cycle, self.site), allowed_mentions=discord.AllowedMentions.none())
                self.store.mark(key)
        for key, channel_key, war, title in events:
            if self.store.sent(key):
                continue
            channel = self.manager.channel(channel_key)
            if channel is None:
                continue
            beacon_role = self.manager.role("beacons") if title else None
            mentions = discord.AllowedMentions(
                everyone=False,
                users=False,
                roles=[beacon_role] if beacon_role else False,
            )
            await channel.send(
                content=beacon_role.mention if beacon_role else None,
                embed=war_embed(war, self.site, title),
                allowed_mentions=mentions,
            )
            self.store.mark(key)
        await self.card("hall", "hall", hall_embed(data, self.site))


def hall_embed(data, site):
    embed = discord.Embed(title="Зал славы", colour=GOLD, url=site)
    for season in data["hall"][:3]:
        text = "\n".join(
            f"{r['rank']}. {safe(r['name'], 120)} · {r['territories']} земель"
            for r in season["results"]
        )
        embed.add_field(
            name=safe(season["name"]),
            value=text[:1024] or "Нет результатов.",
            inline=False,
        )
    if not embed.fields:
        embed.description = "Здесь появятся победители завершённых сезонов."
    return embed


def weekly_embed(data, site):
    wars = [w for w in data["wars"] if w["status"] == "completed"]
    text = "\n".join(
        f"**{safe(w['territory'], 80)}** — {safe(w['winner'], 80)}" for w in wars[-15:]
    )
    return discord.Embed(
        title="Хроника недели",
        description=text or "За неделю нет завершённых войн.",
        colour=GOLD,
        url=site,
    )
