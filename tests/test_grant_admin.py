from app.core.security import verify_password
from app.models.operation import AdminAuditLog
from app.models.role import Role
from app.services.user_service import UserService
from app.schemas.user import UserCreate
from deploy.grant_admin import grant_admin


def test_grant_admin_creates_audited_login(db):
    user = grant_admin(db, "darcks", "admin")

    assert user.username == "clanwar"
    assert user.role.name == "admin"
    assert user.is_active is True
    assert user.is_claimed is True
    assert verify_password("admin", user.hashed_password)
    assert db.query(AdminAuditLog).filter(
        AdminAuditLog.action == "admin_account_created"
    ).count() == 1


def test_grant_admin_updates_existing_user_without_duplicate(db):
    db.add(Role(id=2, name="user", description="Обычный пользователь"))
    db.commit()
    existing = UserService().create_user(
        db,
        UserCreate(
            username="Darcks",
            email="clanwar@example.com",
            password="old-password",
        ),
    )

    updated = grant_admin(
        db,
        "darcks",
        "admin",
        email="clanwar@ennorath.com",
    )

    assert updated.id == existing.id
    assert db.query(type(existing)).count() == 1
    assert updated.username == "clanwar"
    assert updated.email == "clanwar@ennorath.com"
    assert updated.role.name == "admin"
    assert verify_password("admin", updated.hashed_password)
