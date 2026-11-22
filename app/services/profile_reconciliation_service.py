"""Absorb imported, unclaimed profiles into a verified Arena account."""
from sqlalchemy import func, or_, select

from app.database import Base
from app.models.achievement import UserAchievement
from app.models.auth_session import SecurityAuditEvent
from app.models.external_identity import ExternalPlayerAlias, ExternalPlayerIdentity
from app.models.match import Match, MatchParticipant
from app.models.notification import UserNotification
from app.models.user import User


class ProfileReconciliationService:
    def reconcile(self, db, identity):
        if identity.verification_status != "verified" or not identity.user.is_claimed:
            return []
        db.flush()
        target = db.query(User).filter(User.id == identity.user_id).with_for_update().one()
        names = {row[0] for row in db.query(ExternalPlayerAlias.nickname).filter_by(identity_id=identity.id)}
        names.add(identity.current_nickname)
        sources = db.query(User).filter(
            User.id != target.id, User.is_claimed.is_(False),
            func.lower(User.username).in_({name.lower() for name in names}),
        ).order_by(User.id).with_for_update().all()
        merged = []
        for source in sources:
            if not self._is_placeholder(db, source, identity.external_uuid):
                continue
            old_id, old_name = source.id, source.username
            self._move_progress(db, source, target)
            db.query(UserNotification).filter_by(user_id=source.id).update(
                {UserNotification.user_id: target.id}, synchronize_session=False,
            )
            db.flush()
            # All incoming references were checked above and explicitly moved.
            db.query(User).filter_by(id=source.id).delete(synchronize_session="fetch")
            db.add(SecurityAuditEvent(
                user_id=target.id, event_type="arena_profile_reconciled",
                event_metadata={"source_user_id": old_id, "source_username": old_name,
                                "external_uuid": identity.external_uuid},
            ))
            merged.append(old_id)
        db.flush()
        occupied = db.query(User.id).filter(
            User.id != target.id,
            func.lower(User.username) == identity.current_nickname.lower(),
        ).first()
        name_keys = {name.lower() for name in names}
        generated_or_public_name = (
            target.username.lower() in name_keys
            or target.username.rsplit("~", 1)[0].lower() in name_keys
        )
        if occupied is None and generated_or_public_name:
            target.username = identity.current_nickname
        self.canonicalize_matches(db, identity, names)
        db.flush()
        return merged

    def canonicalize_matches(self, db, identity, names):
        keys = {name.lower() for name in names}
        keys.difference_update(name.lower() for (name,) in db.query(User.username).filter(
            User.id != identity.user_id, User.is_claimed.is_(True),
            func.lower(User.username).in_(keys),
        ))
        keys.difference_update(name.lower() for (name,) in db.query(ExternalPlayerAlias.nickname)
                               .join(ExternalPlayerIdentity).filter(
                                   ExternalPlayerIdentity.id != identity.id,
                                   func.lower(ExternalPlayerAlias.nickname).in_(keys),
                               ))
        # Historical aliases are internal lookup keys, never separate leaderboard entries.
        for model, name_column, uuid_column in (
            (Match, Match.winner_player, Match.winner_player_uuid),
            (Match, Match.loser_player, Match.loser_player_uuid),
            (MatchParticipant, MatchParticipant.nickname, MatchParticipant.player_uuid),
        ):
            db.query(model).filter(
                or_(
                    uuid_column == identity.external_uuid,
                    (func.lower(name_column).in_(keys)) &
                    (uuid_column.is_(None) | (uuid_column == "")),
                ),
                (name_column != identity.current_nickname) | uuid_column.is_(None) | (uuid_column == ""),
            ).update({name_column: identity.current_nickname, uuid_column: identity.external_uuid},
                     synchronize_session="fetch")

    def _is_placeholder(self, db, user, external_uuid):
        # Do not move registered accounts, linked UUIDs, sessions, inventory,
        # memberships, or any new relationship without a dedicated merge policy.
        if user.is_claimed or user.hashed_password not in (None, "", "!"):
            return False
        for table in Base.metadata.sorted_tables:
            if table.name in {"user_achievements", "user_notifications"}:
                continue
            for column in table.columns:
                if any(fk.target_fullname == "users.id" for fk in column.foreign_keys):
                    if db.execute(select(column).where(column == user.id).limit(1)).first():
                        return False
        nickname = user.username.lower()
        if db.query(MatchParticipant.id).filter(
            func.lower(MatchParticipant.nickname) == nickname,
            MatchParticipant.player_uuid.isnot(None),
            MatchParticipant.player_uuid != external_uuid,
        ).first():
            return False
        return db.query(Match.id).filter(or_(
            (func.lower(Match.winner_player) == nickname) &
            Match.winner_player_uuid.isnot(None) & (Match.winner_player_uuid != external_uuid),
            (func.lower(Match.loser_player) == nickname) &
            Match.loser_player_uuid.isnot(None) & (Match.loser_player_uuid != external_uuid),
        )).first() is None

    def _move_progress(self, db, source, target):
        existing = {row.achievement_id: row for row in db.query(UserAchievement).filter_by(user_id=target.id)}
        duplicate_rewards = 0
        for row in db.query(UserAchievement).filter_by(user_id=source.id).all():
            saved = existing.get(row.achievement_id)
            if saved is None:
                row.user_id = target.id
                existing[row.achievement_id] = row
                continue
            if saved.is_completed and row.is_completed:
                duplicate_rewards += row.achievement.reward_amount or 0
            saved.progress = max(saved.progress or 0, row.progress or 0)
            saved.is_completed = saved.is_completed or row.is_completed
            times = [value for value in (saved.completed_at, row.completed_at) if value is not None]
            saved.completed_at = min(times) if times else None
            db.delete(row)
        target.balance = (target.balance or 0) + max(0, (source.balance or 0) - duplicate_rewards)
        target.experience = max(target.experience or 0, source.experience or 0)
        target.level = max(target.level or 1, source.level or 1)
