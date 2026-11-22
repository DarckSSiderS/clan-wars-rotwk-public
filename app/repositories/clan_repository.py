from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.clan import Clan, ClanMember, ClanInvite, ClanApplication
from app.repositories.base import BaseRepository

class ClanRepository(BaseRepository[Clan]):
    def __init__(self):
        super().__init__(Clan)
    
    def get_by_name(self, db: Session, name: str) -> Optional[Clan]:
        """Получить клан по названию"""
        return self.get_by_field(db, "name", name)
    
    def get_with_member_count(self, db: Session, skip: int = 0, limit: int = 100) -> List[Clan]:
        """Получить кланы с количеством участников"""
        clans = (
            db.query(Clan)
            .filter(Clan.is_deleted.is_(False))
            .offset(skip)
            .limit(limit)
            .all()
        )
        
        # Подсчитываем количество участников для каждого клана
        for clan in clans:
            member_count = db.query(ClanMember).filter(ClanMember.clan_id == clan.id).count()
            clan.member_count = member_count
        
        return clans

    def get_with_member_count_single(self, db: Session, clan_id: int) -> Optional[Clan]:
        """Получить клан с количеством участников по ID"""
        clan = self.get(db, clan_id)
        if clan:
            member_count = db.query(ClanMember).filter(ClanMember.clan_id == clan.id).count()
            clan.member_count = member_count
        return clan

class ClanMemberRepository(BaseRepository[ClanMember]):
    def __init__(self):
        super().__init__(ClanMember)
    
    def get_by_user_and_clan(self, db: Session, user_id: int, clan_id: int) -> Optional[ClanMember]:
        """Получить участника клана по пользователю и клану"""
        return db.query(ClanMember).filter(
            ClanMember.user_id == user_id,
            ClanMember.clan_id == clan_id
        ).first()
    
    def get_clan_members(self, db: Session, clan_id: int) -> List[dict]:
        """Получить всех участников клана с данными пользователей"""
        from app.models.war import ClanWar
        from app.models.war_deployment import WarDeployment

        members = db.query(ClanMember).join(ClanMember.user).filter(ClanMember.clan_id == clan_id).all()
        busy_warlords = {
            user_id
            for (user_id,) in (
                db.query(WarDeployment.warlord_user_id)
                .join(ClanWar, ClanWar.id == WarDeployment.war_id)
                .filter(
                    WarDeployment.clan_id == clan_id,
                    WarDeployment.current_role == "attacker",
                    WarDeployment.warlord_user_id.isnot(None),
                    ClanWar.status == "active",
                )
                .all()
            )
        }
        result = []
        for member in members:
            member_dict = {
                'id': member.id,
                'user_id': member.user_id,
                'clan_id': member.clan_id,
                'rank': member.rank,
                'joined_at': member.joined_at,
                'is_trader': member.is_trader,
                'is_warlord': member.is_warlord,
                'warlord_busy': member.user_id in busy_warlords,
                'username': member.user.username if member.user else None,
                'avatar_url': member.user.avatar_url if member.user else None
            }
            result.append(member_dict)
        return result
    
    def get_user_clan(self, db: Session, user_id: int) -> Optional[ClanMember]:
        """Получить клан пользователя"""
        return db.query(ClanMember).filter(ClanMember.user_id == user_id).first()

class ClanInviteRepository(BaseRepository[ClanInvite]):
    def __init__(self):
        super().__init__(ClanInvite)
    
    def get_user_invites(self, db: Session, user_id: int) -> List[dict]:
        """Получить приглашения пользователя"""
        from app.models.user import User
        from app.models.clan import Clan
        from sqlalchemy.orm import aliased
        
        print(f"ClanInviteRepository.get_user_invites called for user_id: {user_id}")
        
        # Создаем алиасы для разных ролей пользователей
        Inviter = aliased(User)
        Invitee = aliased(User)
        
        invites = db.query(ClanInvite).join(
            Clan, ClanInvite.clan_id == Clan.id
        ).join(
            Inviter, ClanInvite.inviter_id == Inviter.id
        ).join(
            Invitee, ClanInvite.invitee_id == Invitee.id
        ).filter(
            ClanInvite.invitee_id == user_id,
            ClanInvite.status == "pending"
        ).all()
        
        print(f"Found {len(invites)} raw invites")
        
        # Преобразуем в словари с нужными полями для схемы ClanInviteWithDetails
        result = []
        for invite in invites:
            invite_dict = {
                'id': invite.id,
                'clan_id': invite.clan_id,
                'inviter_id': invite.inviter_id,
                'invitee_id': invite.invitee_id,
                'message': invite.message,
                'status': invite.status,
                'created_at': invite.created_at,
                'clan_name': invite.clan.name if invite.clan else "Неизвестный клан",
                'inviter_username': invite.inviter.username if invite.inviter else "Неизвестный пользователь",
                'invitee_username': invite.invitee.username if invite.invitee else "Неизвестный пользователь"
            }
            result.append(invite_dict)
        
        print(f"Returning {len(result)} processed invites")
        return result
    
    def get_clan_invites(self, db: Session, clan_id: int) -> List[ClanInvite]:
        """Получить приглашения клана"""
        return db.query(ClanInvite).filter(ClanInvite.clan_id == clan_id).all()

class ClanApplicationRepository(BaseRepository[ClanApplication]):
    def __init__(self):
        super().__init__(ClanApplication)
    
    def get_pending_applications(self, db: Session, clan_id: int) -> List[dict]:
        """Получить ожидающие заявки клана с дополнительными данными"""
        from app.models.user import User
        from app.models.clan import Clan
        
        applications = db.query(ClanApplication).join(
            User, ClanApplication.user_id == User.id
        ).join(
            Clan, ClanApplication.clan_id == Clan.id
        ).filter(
            ClanApplication.clan_id == clan_id,
            ClanApplication.status == "pending"
        ).all()
        
        result = []
        for application in applications:
            application_dict = {
                'id': application.id,
                'clan_id': application.clan_id,
                'user_id': application.user_id,
                'message': application.message,
                'status': application.status,
                'created_at': application.created_at,
                'reviewed_at': application.reviewed_at,
                'reviewed_by': application.reviewed_by,
                'clan_name': application.clan.name if application.clan else "Неизвестный клан",
                'user_username': application.user.username if application.user else "Неизвестный пользователь",
                'user': {
                    'id': application.user.id if application.user else None,
                    'username': application.user.username if application.user else "Неизвестный пользователь",
                    'avatar_url': application.user.avatar_url if application.user else None
                }
            }
            result.append(application_dict)
        
        return result
    
    def get_user_application(self, db: Session, user_id: int, clan_id: int) -> Optional[ClanApplication]:
        """Получить заявку пользователя в клан"""
        return db.query(ClanApplication).filter(
            ClanApplication.user_id == user_id,
            ClanApplication.clan_id == clan_id
        ).first()

    def get_clan_applications(self, db: Session, clan_id: int) -> List[ClanApplication]:
        """Получить все заявки клана"""
        return db.query(ClanApplication).filter(ClanApplication.clan_id == clan_id).all() 
