"""One-time Discord proof confirmed by an authenticated website account."""

from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.models.discord import DiscordLink, DiscordLinkCode
from app.models.user import User


class LinkError(ValueError):
    pass


def _hash(code):
    return hashlib.sha256(code.strip().encode()).hexdigest()


def issue_link_code(db, discord_id, now=None):
    now = now or datetime.now(timezone.utc)
    discord_id = str(discord_id)
    if not re.fullmatch(r"[1-9][0-9]{16,19}", discord_id) or int(discord_id) >= 2**64:
        raise LinkError("Некорректный Discord ID.")
    code = secrets.token_urlsafe(24)
    db.execute(delete(DiscordLinkCode).where(DiscordLinkCode.expires_at <= now))
    db.execute(
        delete(DiscordLinkCode).where(DiscordLinkCode.discord_user_id == discord_id)
    )
    db.add(
        DiscordLinkCode(
            discord_user_id=discord_id,
            code_hash=_hash(code),
            expires_at=now + timedelta(minutes=10),
        )
    )
    db.commit()
    return code


def consume_link_code(db, user, code, now=None):
    now = now or datetime.now(timezone.utc)
    # Serialize issuance of a user's identity as well as consuming the challenge.
    account = db.execute(
        select(User).where(User.id == user.id).with_for_update()
    ).scalar_one()
    if not account.is_active or not account.is_claimed:
        raise LinkError("Для привязки нужен активный подтверждённый аккаунт.")
    if db.get(DiscordLink, account.id):
        raise LinkError("Сначала отключите текущую привязку Discord.")
    try:
        discord_id = db.execute(
            delete(DiscordLinkCode)
            .where(
                DiscordLinkCode.code_hash == _hash(code),
                DiscordLinkCode.expires_at > now,
            )
            .returning(DiscordLinkCode.discord_user_id)
        ).scalar_one_or_none()
        if discord_id is None:
            raise LinkError(
                "Код неверен, уже использован или истёк. Получите новый через /link."
            )
        link = DiscordLink(
            user_id=account.id, discord_user_id=discord_id, created_at=now
        )
        db.add(link)
        db.commit()
        return link
    except IntegrityError as exc:
        db.rollback()
        raise LinkError("Этот Discord уже привязан к другому аккаунту.") from exc
    except LinkError:
        db.rollback()
        raise


def unlink(db, user_id):
    link = db.get(DiscordLink, user_id)
    if link:
        db.execute(
            delete(DiscordLinkCode).where(
                DiscordLinkCode.discord_user_id == link.discord_user_id
            )
        )
        db.delete(link)
        db.commit()
