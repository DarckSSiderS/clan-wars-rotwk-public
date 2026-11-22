"""Replace synthetic ladder rows with a small verified source sample.

This is a local bootstrap helper for the demo database. The production sync
continues to read display names directly from the ladder HTML.
"""

from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.security import get_password_hash
from app.database import SessionLocal
from app.models.match import Match
from app.models.role import Role
from app.models.user import User


REAL_MATCHES = [
    {
        "match_id": "b1821c70-77a2-42ca-a866-2f20f33259c3.BfME2Replay",
        "winner_player": "Ar-Adunaim", "winner_faction": "Lothlorien",
        "loser_player": "KaHuCTPa", "loser_faction": "Isengard",
        "map_name": "Brandy Hills", "duration": "00:16:51",
        "match_date": "2026/07/13 02:23",
    },
    {
        "match_id": "6646bca3-3b88-4191-8074-5c41a87c16c7.BfME2Replay",
        "winner_player": "monro", "winner_faction": "Goblins",
        "loser_player": "BurMister", "loser_faction": "Goblins",
        "map_name": "Fords of Isen (Unlame)", "duration": "00:27:31",
        "match_date": "2026/07/13 02:14",
    },
    {
        "match_id": "567ecef7-cedf-48cf-918a-7ab2a703e454.BfME2Replay",
        "winner_player": "BurMister", "winner_faction": "Gondor",
        "loser_player": "monro", "loser_faction": "Isengard",
        "map_name": "Plains of Lindon", "duration": "00:25:55",
        "match_date": "2026/07/13 01:46",
    },
    {
        "match_id": "fa6eca6f-c704-4803-b375-49aed0bfd702.BfME2Replay",
        "winner_player": "Strider...", "winner_faction": "Imladris",
        "loser_player": "Ar-Adunaim", "loser_faction": "Goblins",
        "map_name": "Rhudaur", "duration": "00:37:51",
        "match_date": "2026/07/13 01:43",
    },
    {
        "match_id": "4c575581-d107-4d54-94e9-b25ea8a97d8e.BfME2Replay",
        "winner_player": "BurMister", "winner_faction": "Mordor",
        "loser_player": "Ar-Adunaim", "loser_faction": "Gondor",
        "map_name": "Chetwood", "duration": "00:19:03",
        "match_date": "2026/07/13 01:15",
    },
]

REAL_PLAYERS = {
    "Ar-Adunaim": "ar-adunaim@ladder.local",
    "KaHuCTPa": "kahuctpa@ladder.local",
    "BurMister": "burmister@ladder.local",
    "monro": "monro@ladder.local",
    "Strider...": "strider@ladder.local",
}


def get_role(db, name, description):
    role = db.query(Role).filter(Role.name == name).first()
    if role:
        return role
    role = Role(name=name, description=description)
    db.add(role)
    db.flush()
    return role


def ensure_player(db, username, email, role):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            username=username,
            email=email,
            hashed_password=get_password_hash("ladder123"),
            is_active=True,
            role_id=role.id,
            language="ru",
        )
        db.add(user)
    else:
        user.username = username
        user.email = email
        user.role_id = role.id
        user.is_active = True
    return user


def main():
    db = SessionLocal()
    try:
        admin_role = get_role(db, "admin", "Local administrator")
        user_role = get_role(db, "user", "Local user")

        # Keep the existing admin row and expose it under a real source nickname.
        admin = db.query(User).filter(User.username == "admin").first()
        source_admin = db.query(User).filter(User.username == "Ar-Adunaim").first()
        if admin and source_admin and admin.id != source_admin.id:
            admin.username = "legacy_admin"
            admin.email = "legacy-admin@example.com"
        source_admin = source_admin or admin
        if not source_admin:
            source_admin = User(email="ar-adunaim@ladder.local")
            db.add(source_admin)
        source_admin.username = "Ar-Adunaim"
        source_admin.email = "admin@example.com"
        source_admin.hashed_password = get_password_hash("admin")
        source_admin.role_id = admin_role.id
        source_admin.is_active = True

        # Remove only rows that were created from the old placeholder naming scheme.
        fake_matches = db.query(Match).filter(
            (Match.winner_player.like("player_%")) |
            (Match.loser_player.like("player_%"))
        ).all()
        for match in fake_matches:
            db.delete(match)

        for username, email in REAL_PLAYERS.items():
            if username != "Ar-Adunaim":
                ensure_player(db, username, email, user_role)

        db.flush()
        for item in REAL_MATCHES:
            match = db.query(Match).filter(Match.match_id == item["match_id"]).first()
            if not match:
                match = Match(match_id=item["match_id"])
                db.add(match)
            for key, value in item.items():
                if key == "match_date":
                    value = datetime.strptime(value, "%Y/%m/%d %H:%M")
                setattr(match, key, value)
            match.game_name = "RotWK"
            match.game_mode = "1 versus 1"
            match.gamemode_name = "1 versus 1"
            match.patch_version = "Ennorath (1.9.7.7d)"
            match.patch_name = "Ennorath"
            match.is_live = False
            match.is_valid = True

        # Old placeholder accounts should not be presented as active players.
        fake_users = db.query(User).filter(User.username.like("player_%")).all()
        for user in fake_users:
            user.username = f"archived_{user.id}"
            user.is_active = False

        db.commit()
        print({
            "admin": "Ar-Adunaim",
            "removed_fake_matches": len(fake_matches),
            "real_sample_matches": len(REAL_MATCHES),
            "real_players": list(REAL_PLAYERS),
        })
    finally:
        db.close()


if __name__ == "__main__":
    main()
