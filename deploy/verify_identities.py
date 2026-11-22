from app.database import SessionLocal
from app.models.external_identity import ExternalPlayerAlias, ExternalPlayerIdentity
from app.models.match import Match
from app.models.user import User
from sqlalchemy import func


def main() -> None:
    db = SessionLocal()
    try:
        latest = (
            db.query(
                ExternalPlayerIdentity.current_nickname,
                ExternalPlayerIdentity.verification_status,
            )
            .order_by(ExternalPlayerIdentity.id.desc())
            .first()
        )
        print(
            {
                "matches_with_winner_uuid": (
                    db.query(Match)
                    .filter(Match.winner_player_uuid.isnot(None))
                    .count()
                ),
                "identities": db.query(ExternalPlayerIdentity).count(),
                "aliases": db.query(ExternalPlayerAlias).count(),
                "identity_statuses": dict(
                    db.query(
                        ExternalPlayerIdentity.verification_status,
                        func.count(ExternalPlayerIdentity.id),
                    )
                    .group_by(ExternalPlayerIdentity.verification_status)
                    .all()
                ),
                "claimed_active_users": (
                    db.query(User)
                    .filter(
                        User.is_claimed.is_(True),
                        User.is_active.is_(True),
                    )
                    .count()
                ),
                "claimed_users_with_identity": (
                    db.query(func.count(func.distinct(ExternalPlayerIdentity.user_id)))
                    .join(User, User.id == ExternalPlayerIdentity.user_id)
                    .filter(
                        User.is_claimed.is_(True),
                        User.is_active.is_(True),
                    )
                    .scalar()
                    or 0
                ),
                "latest_identity": latest,
            }
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
