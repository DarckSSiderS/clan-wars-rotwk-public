"""Repair operator-confirmed legacy aliases. Dry run unless --apply is set.

Run from project root: python -m scripts.reconcile_arena_profile --help
Player names are canonicalized; scores and war ledgers are not rewritten.
The verified account ID survives.
"""
import argparse
import json

from sqlalchemy import event, func
from sqlalchemy.orm import Session

from app.database import engine
import app.models  # noqa: F401
from app.models.auth_session import SecurityAuditEvent
from app.models.external_identity import ExternalPlayerAlias, ExternalPlayerIdentity
from app.models.user import User
from app.services.achievement_service import UserAchievementService
from app.services.external_identity_service import ExternalIdentityService
from app.services.profile_reconciliation_service import ProfileReconciliationService
from app.services.user_service import UserService
from app.services.realtime_service import _publish_committed_events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uuid", required=True)
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument("--alias", action="append", required=True)
    parser.add_argument("--full-history", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    # Service commits release savepoints, not the outer repair transaction.
    # Publish notifications only after the real commit, never during a dry run.
    event.remove(Session, "after_commit", _publish_committed_events)
    with engine.connect() as connection:
        transaction = connection.begin()
        db = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            identity = db.query(ExternalPlayerIdentity).filter_by(
                source="bfmeladder", external_uuid=args.uuid, user_id=args.user_id,
                verification_status="verified",
            ).with_for_update().one()
            user = identity.user
            service = ProfileReconciliationService()
            before_names = ExternalIdentityService().names_for_user(db, user.id)
            for name in args.alias:
                conflicts = db.query(ExternalPlayerIdentity).join(ExternalPlayerAlias).filter(
                    func.lower(ExternalPlayerAlias.nickname) == name.lower(),
                    ExternalPlayerIdentity.id != identity.id,
                ).first()
                if conflicts:
                    raise ValueError("Alias belongs to another Arena identity")
                candidates = db.query(User).filter(
                    func.lower(User.username) == name.lower(), User.id != user.id,
                ).all()
                if any(not service._is_placeholder(db, candidate, args.uuid) for candidate in candidates):
                    raise ValueError("Source account has conflicting identity or unsupported personal data")
                if name not in before_names:
                    db.add(ExternalPlayerAlias(identity_id=identity.id, nickname=name))
            old_mode = user.history_mode
            if args.full_history:
                user.history_mode = "full"
                user.statistics_started_at = None
            merged = service.reconcile(db, identity)
            db.add(SecurityAuditEvent(
                user_id=user.id, event_type="arena_legacy_alias_repair",
                event_metadata={"aliases": args.alias, "merged_user_ids": merged,
                                "previous_history_mode": old_mode, "history_mode": user.history_mode},
            ))
            db.commit()
            UserAchievementService().sync_user_achievements(db, user.id)
            db.commit()
            output = {
                "applied": args.apply, "user_id": user.id, "username": user.username,
                "merged_user_ids": merged, "history_mode": user.history_mode,
                "aliases": sorted(ExternalIdentityService().names_for_user(db, user.id)),
                "statistics": UserService().get_user_statistics(db, user.username),
                "completed_achievements": sum(row.is_completed for row in user.achievements),
                "balance": user.balance,
            }
            db.commit()
            if args.apply:
                transaction.commit()
                _publish_committed_events(db)
            else:
                transaction.rollback()
            print(json.dumps(output, ensure_ascii=False))
        except Exception:
            transaction.rollback()
            raise
        finally:
            db.close()
            event.listen(Session, "after_commit", _publish_committed_events)


if __name__ == "__main__":
    main()
