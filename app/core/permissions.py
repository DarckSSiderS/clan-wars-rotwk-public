from enum import Enum

from sqlalchemy.orm import Session

from app.core.exceptions import ClanNotFoundException, InsufficientPermissionsException
from app.models.clan import Clan, ClanMember
from app.models.user import User


class ClanPermission(str, Enum):
    VIEW_PRIVATE = "view_private"
    MANAGE_CLAN = "manage_clan"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_ROLES = "manage_roles"
    DECLARE_WAR = "declare_war"
    MANAGE_TERRITORY = "manage_territory"
    MANAGE_RELICS = "manage_relics"
    MANAGE_MARKET = "manage_market"


ALL_CLAN_PERMISSIONS = set(ClanPermission)
ROLE_PERMISSIONS = {
    "глава клана": ALL_CLAN_PERMISSIONS,
    "лидер": ALL_CLAN_PERMISSIONS,
    "торговец": {
        ClanPermission.VIEW_PRIVATE,
        ClanPermission.MANAGE_MARKET,
    },
    "воин": {
        ClanPermission.VIEW_PRIVATE,
    },
    "участник": {
        ClanPermission.VIEW_PRIVATE,
    },
    "салага": {
        ClanPermission.VIEW_PRIVATE,
    },
    "новичок": {
        ClanPermission.VIEW_PRIVATE,
    },
}


def is_admin(user: User) -> bool:
    return bool(
        getattr(user, "_is_admin_impersonation", False)
        or (user.role and user.role.name == "admin")
    )


def get_clan_membership(db: Session, clan_id: int, user_id: int) -> ClanMember | None:
    return db.query(ClanMember).filter(
        ClanMember.clan_id == clan_id,
        ClanMember.user_id == user_id,
    ).first()


def get_effective_clan_role(clan: Clan, member: ClanMember) -> str:
    if clan.leader_id == member.user_id:
        return "глава клана"
    if member.is_trader:
        return "торговец"
    return (member.rank or "салага").strip().lower()


def require_clan_permission(
    db: Session,
    clan_id: int,
    user: User,
    permission: ClanPermission,
) -> tuple[Clan, ClanMember | None]:
    clan = db.query(Clan).filter(Clan.id == clan_id).first()
    if not clan:
        raise ClanNotFoundException(clan_id)

    if is_admin(user):
        member = get_clan_membership(db, clan_id, user.id)
        return clan, member

    member = get_clan_membership(db, clan_id, user.id)
    if not member:
        raise InsufficientPermissionsException("выполнить действие в чужом клане")

    role = get_effective_clan_role(clan, member)
    if permission not in ROLE_PERMISSIONS.get(role, set()):
        raise InsufficientPermissionsException(
            f"выполнить действие клана: для роли «{member.rank or role}» нет нужного разрешения"
        )
    return clan, member
