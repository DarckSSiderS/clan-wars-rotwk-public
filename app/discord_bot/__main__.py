"""Explicit launch only: importing FastAPI never connects a Discord bot."""

import argparse
import logging
from urllib.parse import urlsplit

import discord
from sqlalchemy import inspect

from app.config import settings
from app.database import engine


def invite_url():
    permissions = discord.Permissions(
        view_channel=True,
        send_messages=True,
        embed_links=True,
        attach_files=True,
        read_message_history=True,
        manage_channels=True,
        manage_roles=True,
        create_public_threads=True,
        send_messages_in_threads=True,
        manage_threads=True,
        connect=True,
        move_members=True,
    )
    kwargs = {"permissions": permissions, "scopes": ("bot", "applications.commands")}
    if settings.DISCORD_GUILD_ID:
        kwargs.update(
            guild=discord.Object(id=settings.DISCORD_GUILD_ID),
            disable_guild_select=True,
        )
    return discord.utils.oauth_url(settings.DISCORD_APPLICATION_ID, **kwargs)


def check_configuration():
    errors = []
    if not settings.DISCORD_ENABLED:
        errors.append("DISCORD_ENABLED=false: интеграция выключена")
    if not settings.DISCORD_BOT_TOKEN.get_secret_value():
        errors.append("DISCORD_BOT_TOKEN не задан")
    if settings.DISCORD_GUILD_ID <= 0:
        errors.append("DISCORD_GUILD_ID не задан")
    parsed = urlsplit(settings.DISCORD_SITE_URL)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.query
        or parsed.fragment
    ):
        errors.append("DISCORD_SITE_URL должен быть адресом сайта без параметров")
    try:
        names = set(inspect(engine).get_table_names())
        missing = {
            "discord_links",
            "discord_link_codes",
            "discord_resources",
            "discord_deliveries",
        } - names
        if missing:
            errors.append("Нужна миграция: alembic upgrade head")
    except Exception:
        errors.append("База данных недоступна: проверьте DATABASE_URL")
    return errors


def main():
    parser = argparse.ArgumentParser(description="Палантир · bfmeCW")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Проверить настройки без подключения к Discord",
    )
    parser.add_argument(
        "--invite",
        action="store_true",
        help="Ссылка приглашения с необходимыми правами",
    )
    args = parser.parse_args()
    if args.invite:
        print(invite_url())
        return 0
    errors = check_configuration()
    if errors:
        for error in errors:
            print(error)
        return 1
    if args.check:
        print("Настройки и таблицы готовы. Токен не проверялся через Discord.")
        return 0
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    from app.discord_bot.bot import Palantir

    Palantir(settings).run(
        settings.DISCORD_BOT_TOKEN.get_secret_value(), log_handler=None
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
