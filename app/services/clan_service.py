from typing import Optional, List
from sqlalchemy import case, delete, or_, select, update
from sqlalchemy.orm import Session
from app.repositories.clan_repository import ClanRepository, ClanMemberRepository, ClanInviteRepository, ClanApplicationRepository
from app.models.clan import Clan, ClanMember, ClanInvite, ClanApplication, ClanMembershipPeriod
from app.models.campaign import CampaignSeason
from app.models.diplomacy import ClanDiplomacyEvent, ClanDiplomaticRelation
from app.models.territory import (
    Territory,
    TerritoryAttackingClans,
    TerritoryDefendingClans,
)
from app.models.user import User
from app.models.war import ClanWar, ClanWarParticipant
from app.models.war_deployment import WarDeployment, WarDeploymentMember
from app.schemas.clan import ClanCreate, ClanUpdate, ClanMemberCreate, ClanInviteCreate, ClanApplicationCreate
from app.core.exceptions import ClanNotFoundException, ClanNameAlreadyExistsException, UserAlreadyInClanException, InsufficientPermissionsException, UserNotFoundException
from app.core.permissions import ClanPermission, is_admin, require_clan_permission
from app.services.clan_membership_service import ClanMembershipService
from app.services.campaign_rule_service import CampaignRuleService
from app.services.clan_level_service import ClanLevelService
from app.services.operation_service import AdminAuditService
from app.services.notification_service import notification_service
from app.core.clan_colors import (
    CLAN_MAP_COLOR_GROUPS,
    CLAN_MAP_COLORS,
)
from app.core.time import as_utc, utc_now

CLAN_MEMBER_ROLES = {"Торговец", "Воин", "Салага"}

class ClanService:
    def __init__(self):
        self.clan_repo = ClanRepository()
        self.member_repo = ClanMemberRepository()
        self.invite_repo = ClanInviteRepository()
        self.application_repo = ClanApplicationRepository()
        self.membership_history = ClanMembershipService()
        self.rule_service = CampaignRuleService()

    def _create_member(
        self,
        db: Session,
        member_data: dict,
        *,
        reason: str,
    ) -> ClanMember:
        from app.services.preseason_service import PreseasonService
        PreseasonService().lock_rosters(db)
        # Членство и снимок достигнутой четвёрки сохраняются одним commit периода.
        member = ClanMember(**member_data)
        db.add(member)
        db.flush()
        self.membership_history.start(db, member, reason=reason)
        return member

    def _remove_member(
        self,
        db: Session,
        member: ClanMember,
        *,
        reason: str,
    ) -> None:
        self.membership_history.end(db, member, reason=reason)
        self.member_repo.remove(db, id=member.id)

    def _ensure_can_join_clan(self, db: Session, user_id: int):
        from app.services.war_service import ClanWarService

        timeout = ClanWarService().get_user_join_timeout(db, user_id)
        if timeout:
            raise InsufficientPermissionsException(
                f"вступить в клан до {timeout.timeout_until.strftime('%d.%m.%Y %H:%M')}"
            )

    def _ensure_clan_has_space(self, db: Session, clan_id: int):
        clan = self.get_clan(db, clan_id)
        if not clan:
            raise ClanNotFoundException(clan_id=clan_id)
        members_count = db.query(ClanMember).filter(ClanMember.clan_id == clan_id).count()
        if members_count >= clan.max_members:
            raise InsufficientPermissionsException("вступить в клан: достигнут лимит участников")
    
    def get_clan(self, db: Session, clan_id: int) -> Optional[Clan]:
        """Получить клан по ID"""
        return self.clan_repo.get(db, clan_id)
    
    def get_clan_by_name(self, db: Session, name: str) -> Optional[Clan]:
        """Получить клан по названию"""
        return self.clan_repo.get_by_name(db, name)
    
    def get_clans(self, db: Session, skip: int = 0, limit: int = 100) -> List[Clan]:
        """Получить список кланов с количеством участников"""
        return self.clan_repo.get_with_member_count(db, skip=skip, limit=limit)

    @staticmethod
    def get_public_level(db: Session, clan: Clan) -> int:
        """Show current thresholds without writing level events during a GET."""
        return ClanLevelService().evaluate(
            db, clan, rule_set=CampaignRuleService().get_active(db), record=False,
        ).level

    @staticmethod
    def _ensure_map_color_available(
        db: Session,
        requested_color: str,
        *,
        excluded_clan_id: int | None = None,
    ) -> None:
        query = db.query(Clan).filter(
            Clan.map_color.isnot(None),
            Clan.is_admin_clan.is_(False),
        )
        if excluded_clan_id is not None:
            query = query.filter(Clan.id != excluded_clan_id)
        for other_clan in query.all():
            if other_clan.map_color == requested_color:
                raise InsufficientPermissionsException(
                    "выбрать цвет клана: этот цвет уже занят"
                )

    def get_map_color_state(
        self,
        db: Session,
        *,
        clan_id: int | None = None,
    ) -> dict:
        clan = self.get_clan(db, clan_id) if clan_id is not None else None
        occupied_colors = [
            color
            for (color,) in (
                db.query(Clan.map_color)
                .filter(
                    Clan.map_color.isnot(None),
                    Clan.is_admin_clan.is_(False),
                    Clan.id != clan_id if clan_id is not None else True,
                )
                .all()
            )
        ]
        blocked_colors = []
        for candidate in sorted(CLAN_MAP_COLORS):
            if candidate in occupied_colors:
                blocked_colors.append({"color": candidate, "reason": "occupied"})

        season_started = db.query(CampaignSeason.id).first() is not None
        can_change_existing = bool(
            not season_started
            and (
                clan is None
                or not clan.map_color
                or not clan.map_color_change_used
            )
        )
        return {
            "groups": [
                {"key": group["key"], "colors": list(group["colors"])}
                for group in CLAN_MAP_COLOR_GROUPS
            ],
            "blocked_colors": blocked_colors,
            "season_started": season_started,
            "can_change_existing": can_change_existing,
        }
    
    def create_clan_pending(
        self,
        db: Session,
        clan: ClanCreate,
        leader_id: int,
    ) -> Clan:
        """Собирает новый клан в текущей транзакции без её фиксации."""
        rules = self.rule_service.get_active(db).values
        self._ensure_can_join_clan(db, leader_id)

        existing_clan = self.clan_repo.get_by_name(db, clan.name)
        if existing_clan:
            raise ClanNameAlreadyExistsException(clan.name)
        if clan.map_color:
            self._ensure_map_color_available(db, clan.map_color)
        
        clan_data = clan.model_dump()
        clan_data["leader_id"] = leader_id
        starting_influence = int(rules["CAMPAIGN_STARTING_INFLUENCE"])
        clan_data["base_influence"] = starting_influence
        clan_data["territory_points"] = starting_influence
        for resource in ("gold", "iron", "wood", "food", "mithril"):
            clan_data[resource] = int(rules[f"CAMPAIGN_STARTING_{resource.upper()}"])
        db_clan = Clan(**clan_data)
        db.add(db_clan)
        db.flush()

        joined_at = utc_now()
        db.add(
            ClanMember(
                user_id=leader_id,
                clan_id=db_clan.id,
                rank="Глава клана",
                joined_at=joined_at,
            )
        )
        db.add(
            ClanMembershipPeriod(
                user_id=leader_id,
                clan_id=db_clan.id,
                started_at=joined_at,
                started_reason="clan_created",
            )
        )
        db.flush()
        return db_clan

    def create_clan(self, db: Session, clan: ClanCreate, leader_id: int) -> Clan:
        """Создаёт новый клан и фиксирует транзакцию."""
        db_clan = self.create_clan_pending(db, clan, leader_id)
        db.commit()
        db.refresh(db_clan)
        return db_clan
    
    def update_clan(
        self,
        db: Session,
        clan_id: int,
        clan_update: ClanUpdate,
        *,
        actor: User | None = None,
    ) -> Optional[Clan]:
        """Обновить клан"""
        clan = self.get_clan(db, clan_id)
        if not clan:
            raise ClanNotFoundException(clan_id=clan_id)
        
        update_data = clan_update.model_dump(exclude_unset=True)
        if clan.is_admin_clan and "map_color" in update_data:
            update_data["map_color"] = None
        requested_color = update_data.get("map_color")
        if requested_color is not None and requested_color != clan.map_color:
            self._ensure_map_color_available(
                db,
                requested_color,
                excluded_clan_id=clan.id,
            )
            if clan.map_color and not (actor and is_admin(actor)):
                if db.query(CampaignSeason.id).first() is not None:
                    raise InsufficientPermissionsException(
                        "изменить цвет клана после начала официальных сезонов"
                    )
                if clan.map_color_change_used:
                    raise InsufficientPermissionsException(
                        "изменить цвет клана повторно: бесплатная смена уже использована"
                    )
                update_data["map_color_change_used"] = True
        return self.clan_repo.update(db, db_obj=clan, obj_in=update_data)
    
    def get_clan_members(self, db: Session, clan_id: int) -> List[ClanMember]:
        """Получить участников клана"""
        return self.member_repo.get_clan_members(db, clan_id)
    
    def get_user_clan(self, db: Session, user_id: int) -> Optional[ClanMember]:
        """Получить клан пользователя"""
        return self.member_repo.get_user_clan(db, user_id)

    def set_member_role(
        self,
        db: Session,
        clan_id: int,
        user_id: int,
        role: str,
        actor: User,
    ) -> ClanMember:
        clan, _ = require_clan_permission(
            db,
            clan_id,
            actor,
            ClanPermission.MANAGE_ROLES,
        )
        if role not in CLAN_MEMBER_ROLES:
            raise InsufficientPermissionsException("назначить неизвестную роль клана")
        if clan.leader_id == user_id:
            raise InsufficientPermissionsException(
                "изменить роль главы клана без передачи лидерства"
            )
        member = self.member_repo.get_by_user_and_clan(db, user_id, clan_id)
        if not member:
            raise UserNotFoundException(user_id=user_id)

        member.rank = role
        member.is_trader = role == "Торговец"
        notification_service.create(
            db,
            user_id=user_id,
            notification_type="clan_role_changed",
            title="Роль в клане изменена",
            message=f"В клане «{clan.name}» вам назначена роль «{role}».",
            link_url=f"/clans/{clan_id}",
            entity_type="clan",
            entity_id=clan_id,
            commit=False,
        )
        notification_service.create_for_clan(
            db,
            clan_id=clan_id,
            notification_type="clan_role_changed",
            title="Изменение роли участника",
            message=f"{member.user.username} теперь выполняет роль «{role}».",
            link_url=f"/clans/{clan_id}",
            entity_type="clan",
            entity_id=clan_id,
            excluded_user_id=user_id,
            commit=False,
        )
        db.commit()
        db.refresh(member)
        return member

    def set_member_warlord(
        self,
        db: Session,
        clan_id: int,
        user_id: int,
        is_warlord: bool,
        actor: User,
    ) -> ClanMember:
        clan = self.get_clan(db, clan_id)
        if not clan:
            raise ClanNotFoundException(clan_id=clan_id)
        if actor.id != clan.leader_id and not is_admin(actor):
            raise InsufficientPermissionsException("назначить Воеводу")

        member = self.member_repo.get_by_user_and_clan(db, user_id, clan_id)
        if not member:
            raise UserNotFoundException(user_id=user_id)
        if bool(member.is_warlord) == bool(is_warlord):
            return member

        if is_warlord:
            rule_set = self.rule_service.get_active(db)
            level = ClanLevelService().evaluate(
                db,
                clan,
                rule_set=rule_set,
                record=False,
            )
            assigned = (
                db.query(ClanMember)
                .filter(
                    ClanMember.clan_id == clan_id,
                    ClanMember.is_warlord.is_(True),
                )
                .count()
            )
            if assigned >= level.level:
                raise InsufficientPermissionsException(
                    f"назначить больше {level.level} Воевод на {level.level} уровне клана"
                )
        else:
            from app.models.war import ClanWar
            from app.models.war_deployment import WarDeployment

            active_command = (
                db.query(WarDeployment.id)
                .join(ClanWar, ClanWar.id == WarDeployment.war_id)
                .filter(
                    WarDeployment.clan_id == clan_id,
                    WarDeployment.warlord_user_id == user_id,
                    WarDeployment.current_role == "attacker",
                    ClanWar.status == "active",
                )
                .first()
            )
            if active_command:
                raise InsufficientPermissionsException(
                    "снять статус Воеводы до завершения его похода"
                )

        member.is_warlord = bool(is_warlord)
        notification_service.create(
            db,
            user_id=user_id,
            notification_type="clan_warlord_changed",
            title="Военная роль изменена",
            message=(
                f"В клане «{clan.name}» вы "
                f"{'назначены Воеводой' if is_warlord else 'больше не являетесь Воеводой'}."
            ),
            link_url=f"/clans/{clan_id}",
            entity_type="clan",
            entity_id=clan_id,
            commit=False,
        )
        notification_service.create_for_clan(
            db,
            clan_id=clan_id,
            notification_type="clan_warlord_changed",
            title="Изменение военного командования",
            message=(
                f"{member.user.username} "
                f"{'назначен Воеводой' if is_warlord else 'снят с должности Воеводы'}."
            ),
            link_url=f"/clans/{clan_id}",
            entity_type="clan",
            entity_id=clan_id,
            excluded_user_id=user_id,
            commit=False,
        )
        db.commit()
        db.refresh(member)
        return member
    
    def add_clan_member(self, db: Session, member: ClanMemberCreate) -> ClanMember:
        """Добавить участника в клан"""
        clan = self.get_clan(db, member.clan_id)
        if not clan:
            raise ClanNotFoundException(clan_id=member.clan_id)
        if clan.is_admin_clan:
            raise InsufficientPermissionsException(
                "вступить в системный клан без назначения администратора"
            )
        self._ensure_can_join_clan(db, member.user_id)
        self._ensure_clan_has_space(db, member.clan_id)

        # Проверяем, что пользователь не состоит уже в клане
        existing_membership = self.member_repo.get_user_clan(db, member.user_id)
        if existing_membership:
            raise UserAlreadyInClanException()
        
        return self._create_member(db, member.model_dump(), reason="member_added")
    
    def remove_clan_member(self, db: Session, clan_id: int, user_id: int) -> bool:
        """Удалить участника из клана"""
        member = self.member_repo.get_by_user_and_clan(db, user_id, clan_id)
        if not member:
            return False
        
        self._remove_member(db, member, reason="member_removed")
        return True
    
    def create_clan_invite(self, db: Session, invite: ClanInviteCreate, inviter_id: int, clan_id: int) -> ClanInvite:
        """Создать приглашение в клан"""
        clan = self.get_clan(db, clan_id)
        if not clan:
            raise ClanNotFoundException(clan_id=clan_id)
        inviter = db.query(User).filter(User.id == inviter_id).first()
        if clan.is_admin_clan and (not inviter or not is_admin(inviter)):
            raise InsufficientPermissionsException(
                "назначить участника системного клана"
            )
        invite_data = invite.model_dump()
        invite_data["inviter_id"] = inviter_id
        invite_data["clan_id"] = clan_id
        created_invite = self.invite_repo.create(db, obj_in=invite_data)
        notification_service.create(
            db,
            user_id=invite.invitee_id,
            notification_type="clan_invite",
            title=f"Приглашение в клан «{clan.name}»",
            message=f"{inviter.username if inviter else 'Игрок'} приглашает вас присоединиться к клану.",
            link_url="/profile",
            entity_type="clan_invite",
            entity_id=created_invite.id,
        )
        return created_invite
    
    def get_user_invites(self, db: Session, user_id: int) -> List[dict]:
        """Получить приглашения пользователя"""
        print(f"ClanService.get_user_invites called for user_id: {user_id}")
        invites = self.invite_repo.get_user_invites(db, user_id)
        print(f"ClanService.get_user_invites returned {len(invites)} invites")
        return invites
    
    def create_clan_application(self, db: Session, clan_id: int, application: ClanApplicationCreate, user_id: int) -> ClanApplication:
        """Создать заявку в клан"""
        clan = self.get_clan(db, clan_id)
        if not clan:
            raise ClanNotFoundException(clan_id=clan_id)
        if clan.is_admin_clan:
            raise InsufficientPermissionsException(
                "подать заявку в системный клан: участников назначает администратор"
            )
        if clan.is_deleted or not clan.is_recruiting:
            raise InsufficientPermissionsException(
                "подать заявку: клан сейчас не ведёт набор"
            )
        # Проверяем, что пользователь не состоит уже в клане
        existing_membership = self.member_repo.get_user_clan(db, user_id)
        if existing_membership:
            raise UserAlreadyInClanException()
        
        # Проверяем, что заявка уже не существует
        existing_application = self.application_repo.get_user_application(db, user_id, clan_id)
        if existing_application:
            return existing_application if existing_application.status == "pending" else None
        
        application_data = application.model_dump()
        application_data["clan_id"] = clan_id
        application_data["user_id"] = user_id
        created_application = self.application_repo.create(db, obj_in=application_data)
        applicant = db.query(User).filter(User.id == user_id).first()
        if clan.leader_id and clan.leader_id != user_id:
            notification_service.create(
                db,
                user_id=clan.leader_id,
                notification_type="clan_application",
                title=f"Новая заявка в «{clan.name}»",
                message=f"{applicant.username if applicant else 'Игрок'} хочет вступить в клан.",
                link_url=f"/clans/{clan.id}",
                entity_type="clan_application",
                entity_id=created_application.id,
            )
        return created_application
    
    def get_pending_applications(self, db: Session, clan_id: int) -> List[ClanApplication]:
        """Получить ожидающие заявки клана"""
        return self.application_repo.get_pending_applications(db, clan_id)
    
    def respond_to_invite(self, db: Session, invite_id: int, user_id: int, status: str) -> bool:
        """Ответить на приглашение в клан"""
        invite = self.invite_repo.get(db, invite_id)
        if not invite or invite.invitee_id != user_id:
            return False
        
        clan = self.get_clan(db, invite.clan_id)
        inviter_id = invite.inviter_id
        responding_user = db.query(User).filter(User.id == user_id).first()

        if status == "accepted":
            inviter = db.query(User).filter(User.id == invite.inviter_id).first()
            if clan and clan.is_admin_clan and (not inviter or not is_admin(inviter)):
                raise InsufficientPermissionsException(
                    "вступить в системный клан без назначения администратора"
                )
            self._ensure_can_join_clan(db, user_id)
            self._ensure_clan_has_space(db, invite.clan_id)
            existing_membership = self.member_repo.get_user_clan(db, user_id)
            if existing_membership:
                raise UserAlreadyInClanException()

            # Добавляем пользователя в клан
            member_data = {
                "user_id": user_id,
                "clan_id": invite.clan_id,
                "rank": "Салага"
            }
            self._create_member(db, member_data, reason="invite_accepted")

            pending_invites = db.query(ClanInvite).filter(
                ClanInvite.invitee_id == user_id,
                ClanInvite.status == "pending"
            ).all()
            for pending_invite in pending_invites:
                db.delete(pending_invite)
            db.commit()
        else:
            self.invite_repo.remove(db, id=invite_id)
        if inviter_id and inviter_id != user_id:
            notification_service.create(
                db,
                user_id=inviter_id,
                notification_type="clan_invite_response",
                title="Приглашение принято" if status == "accepted" else "Приглашение отклонено",
                message=(
                    f"{responding_user.username if responding_user else 'Игрок'} "
                    f"{'вступил в' if status == 'accepted' else 'не принял приглашение в'} "
                    f"клан «{clan.name if clan else 'неизвестный клан'}»."
                ),
                link_url=f"/clans/{clan.id}" if clan else "/clans",
                entity_type="clan",
                entity_id=clan.id if clan else None,
            )
        return True

    def get_clan_with_member_count(self, db: Session, clan_id: int):
        """Получить клан с количеством участников"""
        return self.clan_repo.get_with_member_count_single(db, clan_id)

    def delete_clan(self, db: Session, clan_id: int) -> bool:
        """Архивировать клан, сохранив карту, войны, очки и историю."""
        from app.services.market_service import ClanMarketService
        market = ClanMarketService()
        market.lock_market(db)
        clan = self.get_clan(db, clan_id)
        if not clan:
            return False
        if clan.is_admin_clan:
            raise InsufficientPermissionsException("удалить системный клан")
        if clan.is_deleted:
            return True

        market.cancel_for_clan(db, clan_id)
        deleted_at = utc_now()
        active_war_ids = list(db.scalars(select(ClanWar.id).where(
            ClanWar.status == "active",
            or_(
                ClanWar.attacking_clan_id == clan_id,
                ClanWar.defending_clan_id == clan_id,
            ),
        )).all())
        active_war_territory_ids = list(db.scalars(select(ClanWar.territory_id).where(
            ClanWar.id.in_(active_war_ids),
        )).all()) if active_war_ids else []
        deployment_ids = list(db.scalars(select(WarDeployment.id).where(
            WarDeployment.war_id.in_(active_war_ids),
        )).all()) if active_war_ids else []
        if active_war_ids:
            db.execute(update(ClanWarParticipant).where(
                ClanWarParticipant.war_id.in_(active_war_ids),
            ).values(is_active=False))
        if deployment_ids:
            db.execute(update(WarDeploymentMember).where(
                WarDeploymentMember.deployment_id.in_(deployment_ids),
                WarDeploymentMember.released_at.is_(None),
            ).values(released_at=deleted_at))
            db.execute(update(WarDeployment).where(
                WarDeployment.id.in_(deployment_ids),
                WarDeployment.attack_lock_released_at.is_(None),
            ).values(attack_lock_released_at=deleted_at))
        if active_war_ids:
            db.execute(update(ClanWar).where(
                ClanWar.id.in_(active_war_ids),
            ).values(status="canceled", ended_at=deleted_at))
        db.execute(delete(TerritoryAttackingClans).where(
            TerritoryAttackingClans.clan_id == clan_id,
        ))
        db.execute(delete(TerritoryDefendingClans).where(
            TerritoryDefendingClans.clan_id == clan_id,
        ))
        if active_war_territory_ids:
            db.execute(update(Territory).where(
                Territory.id.in_(active_war_territory_ids),
            ).values(status=case(
                (Territory.owner_clan_id.is_(None), "neutral"),
                else_="active",
            )))

        # Сохранить исходное членство старых составов до удаления ClanMember.
        for member in db.query(ClanMember).filter_by(clan_id=clan_id).all():
            active_period = db.query(ClanMembershipPeriod.id).filter_by(
                user_id=member.user_id, clan_id=clan_id, ended_at=None).first()
            if active_period is None:
                db.add(ClanMembershipPeriod(user_id=member.user_id, clan_id=clan_id,
                    started_at=as_utc(member.joined_at) or deleted_at,
                    started_reason='legacy_backfill', ended_at=deleted_at,
                    ended_reason='clan_deleted'))
        db.execute(update(ClanMembershipPeriod).where(
            ClanMembershipPeriod.clan_id == clan_id,
            ClanMembershipPeriod.ended_at.is_(None),
        ).values(ended_at=deleted_at, ended_reason="clan_deleted"))
        db.execute(delete(ClanInvite).where(ClanInvite.clan_id == clan_id))
        db.execute(delete(ClanApplication).where(ClanApplication.clan_id == clan_id))
        db.execute(delete(ClanMember).where(ClanMember.clan_id == clan_id))

        relations = list(db.scalars(select(ClanDiplomaticRelation).where(or_(
            ClanDiplomaticRelation.clan_low_id == clan_id,
            ClanDiplomaticRelation.clan_high_id == clan_id,
        ))).all())
        for relation in relations:
            previous_status = relation.status
            relation.status = "neutral"
            relation.requested_by_clan_id = None
            relation.updated_by_user_id = None
            if previous_status != "neutral":
                db.add(ClanDiplomacyEvent(
                    relation_id=relation.id,
                    actor_clan_id=clan_id,
                    actor_user_id=None,
                    previous_status=previous_status,
                    new_status="neutral",
                    note="Клан расформирован",
                ))
        clan.is_deleted = True
        clan.deleted_at = deleted_at
        clan.is_recruiting = False
        clan.leader_id = None
        db.commit()
        db.expire_all()
        return True

    def leave_clan(self, db: Session, user_id: int) -> bool:
        """Покинуть клан"""
        member = self.member_repo.get_user_clan(db, user_id)
        if not member:
            return False

        from app.services.war_service import ClanWarService
        ClanWarService().deactivate_user_for_clan_departure(db, user_id, member.clan_id)

        self._remove_member(db, member, reason="left_clan")
        return True

    def transfer_leadership(self, db: Session, clan_id: int, new_leader_id: int) -> bool:
        """Передать лидерство клана"""
        clan = self.get_clan(db, clan_id)
        if not clan:
            return False
        old_leader_id = clan.leader_id
        
        # Обновляем лидера клана
        update_data = {"leader_id": new_leader_id}
        self.clan_repo.update(db, db_obj=clan, obj_in=update_data)
        
        # Обновляем ранг старого лидера
        old_leader_member = self.member_repo.get_by_user_and_clan(db, old_leader_id, clan_id)
        if old_leader_member:
            self.member_repo.update(
                db,
                db_obj=old_leader_member,
                obj_in={"rank": "Воин", "is_trader": False},
            )
        
        # Обновляем ранг нового лидера
        new_leader_member = self.member_repo.get_by_user_and_clan(db, new_leader_id, clan_id)
        if new_leader_member:
            self.member_repo.update(
                db,
                db_obj=new_leader_member,
                obj_in={"rank": "Глава клана", "is_trader": False},
            )
        
        return True

    def respond_to_application(
        self,
        db: Session,
        application_id: int,
        current_user: User,
        status: str,
    ) -> bool:
        """Ответить на заявку в клан"""
        application = self.application_repo.get(db, application_id)
        if not application:
            return False
        clan = self.get_clan(db, application.clan_id)
        if clan and clan.is_admin_clan:
            raise InsufficientPermissionsException(
                "обработать заявку в системный клан"
            )
        
        require_clan_permission(
            db,
            application.clan_id,
            current_user,
            ClanPermission.MANAGE_MEMBERS,
        )
        
        applicant_id = application.user_id
        if status == "accepted":
            self._ensure_can_join_clan(db, application.user_id)
            self._ensure_clan_has_space(db, application.clan_id)
            existing_membership = self.member_repo.get_user_clan(db, application.user_id)
            if existing_membership:
                raise UserAlreadyInClanException()

            # Добавляем пользователя в клан
            member_data = {
                "user_id": application.user_id,
                "clan_id": application.clan_id,
                "rank": "Салага"
            }
            self._create_member(db, member_data, reason="application_accepted")
        
        # Удаляем заявку
        self.application_repo.remove(db, id=application_id)
        notification_service.create(
            db,
            user_id=applicant_id,
            notification_type="clan_application_response",
            title="Заявка принята" if status == "accepted" else "Заявка отклонена",
            message=(
                f"Клан «{clan.name if clan else 'неизвестный клан'}» "
                f"{'принял вас в состав.' if status == 'accepted' else 'отклонил заявку на вступление.'}"
            ),
            link_url=f"/clans/{clan.id}" if clan else "/clans",
            entity_type="clan",
            entity_id=clan.id if clan else None,
        )
        return True 

    def kick_member(self, db: Session, clan_id: int, user_id: int) -> bool:
        """Исключить участника из клана"""
        from app.models.clan import ClanMember
        
        member = db.query(ClanMember).filter(
            ClanMember.clan_id == clan_id,
            ClanMember.user_id == user_id
        ).first()
        
        if member:
            clan = self.get_clan(db, clan_id)
            notification_service.create(
                db,
                user_id=user_id,
                notification_type="clan_member_kicked",
                title="Вы исключены из клана",
                message=f"Вы больше не состоите в клане «{clan.name if clan else clan_id}».",
                link_url="/clans",
                entity_type="clan",
                entity_id=clan_id,
                commit=False,
            )
            notification_service.create_for_clan(
                db,
                clan_id=clan_id,
                notification_type="clan_member_kicked",
                title="Участник покинул состав",
                message=f"{member.user.username} исключён из клана.",
                link_url=f"/clans/{clan_id}",
                entity_type="clan",
                entity_id=clan_id,
                excluded_user_id=user_id,
                commit=False,
            )
            from app.services.war_service import ClanWarService
            ClanWarService().deactivate_user_for_clan_departure(db, user_id, clan_id)
            self.membership_history.end(db, member, reason="kicked")
            db.delete(member)
            db.commit()
            return True
        return False

    def appoint_admin_clan_member(
        self,
        db: Session,
        clan_id: int,
        user_id: int,
        actor: User,
    ) -> ClanMember:
        if not is_admin(actor):
            raise InsufficientPermissionsException(
                "назначить участника системного клана"
            )
        clan = self.get_clan(db, clan_id)
        if not clan:
            raise ClanNotFoundException(clan_id=clan_id)
        if not clan.is_admin_clan:
            raise InsufficientPermissionsException(
                "использовать административное назначение в обычном клане"
            )
        target = db.query(User).filter(User.id == user_id).first()
        if not target:
            raise UserNotFoundException(user_id=user_id)
        existing = self.member_repo.get_user_clan(db, user_id)
        if existing:
            if existing.clan_id == clan_id:
                return existing
            raise UserAlreadyInClanException()

        self._ensure_can_join_clan(db, user_id)
        self._ensure_clan_has_space(db, clan_id)
        member = ClanMember(
            user_id=user_id,
            clan_id=clan_id,
            rank="Воин",
            is_trader=False,
        )
        db.add(member)
        db.flush()
        self.membership_history.start(db, member, reason="admin_appointed")
        AdminAuditService().record(
            db,
            actor_user_id=actor.id,
            action="admin_clan_member_appointed",
            entity_type="clan_member",
            entity_id=member.id,
            after_data={
                "clan_id": clan_id,
                "user_id": user_id,
                "username": target.username,
            },
        )
        db.commit()
        db.refresh(member)
        return member

    def remove_admin_clan_member(
        self,
        db: Session,
        clan_id: int,
        user_id: int,
        actor: User,
    ) -> bool:
        if not is_admin(actor):
            raise InsufficientPermissionsException(
                "исключить участника системного клана"
            )
        clan = self.get_clan(db, clan_id)
        if not clan:
            raise ClanNotFoundException(clan_id=clan_id)
        if not clan.is_admin_clan:
            raise InsufficientPermissionsException(
                "использовать административное исключение в обычном клане"
            )
        if clan.leader_id == user_id:
            raise InsufficientPermissionsException(
                "исключить владельца системного клана"
            )
        member = self.member_repo.get_by_user_and_clan(db, user_id, clan_id)
        if not member:
            return False

        from app.services.war_service import ClanWarService
        ClanWarService().deactivate_user_for_clan_departure(db, user_id, clan_id)
        self.membership_history.end(db, member, reason="admin_removed")
        member_id = member.id
        db.delete(member)
        AdminAuditService().record(
            db,
            actor_user_id=actor.id,
            action="admin_clan_member_removed",
            entity_type="clan_member",
            entity_id=member_id,
            before_data={"clan_id": clan_id, "user_id": user_id},
        )
        db.commit()
        return True

    def reset_admin_clan_sandbox(
        self,
        db: Session,
        clan_id: int,
        actor: User,
    ) -> Clan:
        if not is_admin(actor):
            raise InsufficientPermissionsException(
                "сбросить тестовое состояние системного клана"
            )
        clan = self.get_clan(db, clan_id)
        if not clan:
            raise ClanNotFoundException(clan_id=clan_id)
        if not clan.is_admin_clan:
            raise InsufficientPermissionsException(
                "сбросить тестовое состояние обычного клана"
            )

        from app.services.bootstrap_service import ADMIN_CLAN_INITIAL_RESOURCES
        before_data = {
            key: getattr(clan, key) or 0
            for key in ADMIN_CLAN_INITIAL_RESOURCES
        }
        for key, value in ADMIN_CLAN_INITIAL_RESOURCES.items():
            setattr(clan, key, value)
        from app.services.clan_influence_service import ClanInfluenceService
        ClanInfluenceService().recalculate(db, clan.id)
        clan.next_attack_at = None
        AdminAuditService().record(
            db,
            actor_user_id=actor.id,
            action="admin_clan_sandbox_reset",
            entity_type="clan",
            entity_id=clan.id,
            before_data=before_data,
            after_data={
                **{
                    key: getattr(clan, key) or 0
                    for key in ADMIN_CLAN_INITIAL_RESOURCES
                },
                "next_attack_at": None,
            },
        )
        db.commit()
        db.refresh(clan)
        return clan

    def update_clan_avatar(self, db: Session, clan_id: int, avatar_url: str) -> bool:
        """Обновить аватар клана"""
        from app.models.clan import Clan
        
        clan = db.query(Clan).filter(Clan.id == clan_id).first()
        if clan:
            clan.avatar_url = avatar_url
            db.commit()
            return True
        return False 
