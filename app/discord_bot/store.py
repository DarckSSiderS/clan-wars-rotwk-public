from contextlib import contextmanager
from datetime import datetime, timezone
from sqlalchemy import select
from app.models.discord import DiscordResource, DiscordDelivery


class Store:
    def __init__(self, session_factory, guild_id, *, close_sessions=True):
        self.session_factory = session_factory
        self.guild_id = str(guild_id)
        self.close_sessions = close_sessions

    @contextmanager
    def session(self):
        db = self.session_factory()
        try:
            yield db
        except Exception:
            db.rollback()
            raise
        finally:
            if self.close_sessions:
                db.close()

    def get(self, key, default=None):
        with self.session() as db:
            row = db.get(DiscordResource, (self.guild_id, key))
            return row.value if row else default

    def items(self, prefix):
        with self.session() as db:
            rows = db.execute(
                select(DiscordResource).where(
                    DiscordResource.guild_id == self.guild_id,
                    DiscordResource.key.startswith(prefix),
                )
            ).scalars()
            return {r.key: r.value for r in rows}

    def put(self, key, value):
        with self.session() as db:
            db.merge(DiscordResource(guild_id=self.guild_id, key=key, value=value))
            db.commit()

    def delete(self, key):
        with self.session() as db:
            row = db.get(DiscordResource, (self.guild_id, key))
            if row:
                db.delete(row)
                db.commit()

    def sent(self, key):
        with self.session() as db:
            return db.get(DiscordDelivery, (self.guild_id, key)) is not None

    def mark(self, key):
        with self.session() as db:
            db.merge(
                DiscordDelivery(
                    guild_id=self.guild_id,
                    key=key,
                    delivered_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
