import argparse
import getpass
import os

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.database import SessionLocal
from app.models.operation import AdminAuditLog
from app.models.role import Role
from app.models.user import User


def grant_admin(
    db: Session,
    username: str,
    password: str,
    email: str | None = None,
) -> User:
    username = username.strip()
    if not username:
        raise ValueError("Логин не может быть пустым")
    if not password:
        raise ValueError("Пароль не может быть пустым")

    admin_role = db.query(Role).filter(Role.name == "admin").first()
    if admin_role is None:
        admin_role = Role(
            name="admin",
            description="Администратор системы",
        )
        db.add(admin_role)
        db.flush()

    user = (
        db.query(User)
        .filter(func.lower(User.username) == username.lower())
        .first()
    )
    before_data = None
    if user is None:
        target_email = email or f"{username}@ennorath.com"
        suffix = 1
        while db.query(User).filter(func.lower(User.email) == target_email.lower()).first():
            target_email = f"{username}+{suffix}@ennorath.com"
            suffix += 1
        user = User(
            username=username,
            email=target_email,
            hashed_password=get_password_hash(password),
            is_active=True,
            is_claimed=True,
            role_id=admin_role.id,
            language="ru",
            allow_clan_invites=True,
        )
        db.add(user)
        db.flush()
        action = "admin_account_created"
    else:
        before_data = {
            "username": user.username,
            "role_id": user.role_id,
            "is_active": user.is_active,
            "is_claimed": user.is_claimed,
        }
        user.username = username
        user.hashed_password = get_password_hash(password)
        user.role_id = admin_role.id
        user.is_active = True
        user.is_claimed = True
        if email:
            email_owner = (
                db.query(User)
                .filter(
                    func.lower(User.email) == email.lower(),
                    User.id != user.id,
                )
                .first()
            )
            if email_owner:
                raise ValueError("Указанный email уже используется")
            user.email = email
        db.flush()
        action = "admin_access_granted"

    db.add(
        AdminAuditLog(
            actor_user_id=user.id,
            action=action,
            entity_type="user",
            entity_id=str(user.id),
            before_data=before_data,
            after_data={
                "username": user.username,
                "role": "admin",
                "is_active": True,
                "is_claimed": True,
            },
            reason="Production administrator access requested by project owner",
        )
    )
    db.commit()
    db.refresh(user)
    return user


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or update an Ennorath administrator account."
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--email")
    args = parser.parse_args()

    password = os.environ.get("CLANWAR_ADMIN_PASSWORD")
    if password is None:
        password = getpass.getpass("Admin password: ")

    db = SessionLocal()
    try:
        user = grant_admin(db, args.username, password, args.email)
        print(
            {
                "id": user.id,
                "username": user.username,
                "role": "admin",
                "active": user.is_active,
            }
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
