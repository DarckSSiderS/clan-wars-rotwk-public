"""Явная подготовка нового сезона; GET не создаёт сезон и не выдаёт подарки."""
from sqlalchemy import func

from app.core.campaign_mode import is_interseason
from app.core.time import as_utc
from app.models.campaign import CampaignRuleSet, CampaignSeason
from app.models.clan import Clan
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.models.user import User
from app.models.war import ClanWar
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_economy import RESOURCE_NAMES, UPGRADES
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_income_catalog import INCOME_CATALOG, INCOME_CATALOG_VERSION, prepare_income_profiles
from app.services.cycle_startup_service import CycleStartupService
from app.services.operation_service import AdminAuditService


class CycleSeasonLaunchService:
    @staticmethod
    def _map(db, *, lock=False):
        query = db.query(Territory).order_by(Territory.id)
        rows = query.with_for_update().populate_existing().all() if lock else query.all()
        names = [row.name for row in rows]
        catalog = {entry.name: entry for entry in INCOME_CATALOG}
        if len(names) != len(set(names)) or set(names) != set(catalog):
            raise ValueError('Состав земель карты отличается от утверждённого каталога')
        return [(row, catalog[row.name]) for row in rows]

    def preparation(self, db):
        if not is_interseason(db):
            raise ValueError('Предстоящая карта доступна только в межсезонье')
        return dict(mechanics_version='cycle_v1', upcoming=True, phase='interseason', ready=False,
            clan_id=None, catalog_version=INCOME_CATALOG_VERSION, territories=[
                dict(territory_id=row.id, profile_material=entry.profile_material,
                    daily_income={key: str(getattr(entry.base, key)) for key in RESOURCE_NAMES},
                    levels={branch: 0 for branch in UPGRADES}, max_level=3,
                    influence_value=entry.influence_value, has_port=entry.has_port, is_playable=True)
                for row, entry in self._map(db) if entry.is_playable])

    @staticmethod
    def _result(season):
        return dict(season_id=season.id, season_name=season.name,
                    **season.rules_snapshot['launch_result'])

    def start(self, db, *, actor_user_id, name, command_id, previous_season_id, now):
        actor = db.get(User, actor_user_id)
        if actor is None or not actor.is_active or actor.role is None or actor.role.name != 'admin':
            raise PermissionError('Запуск сезона доступен только администратору')
        name = (name or '').strip()
        if not name or len(name) > 120 or not command_id or len(command_id) > 120:
            raise ValueError('Укажите название сезона и корректный идентификатор команды')
        now = as_utc(now)
        with CycleEconomyStore._atomic(db):
            # Одна существующая строка правил сериализует даже первый запуск без сезонов.
            rules = db.query(CampaignRuleSet).filter_by(is_active=True).with_for_update().populate_existing().one_or_none()
            if rules is None:
                raise ValueError('Перед запуском необходимо опубликовать правила кампании')
            seasons = db.query(CampaignSeason).order_by(CampaignSeason.number.desc()).all()
            for existing in seasons:
                snapshot = existing.rules_snapshot or {}
                if snapshot.get('launch_command_id') == command_id:
                    if existing.created_by_user_id != actor_user_id or existing.name != name or snapshot.get('launch_previous_id') != previous_season_id:
                        raise ValueError('Параметры повторной команды запуска изменились')
                    return self._result(existing)
            if any(season.status != 'completed' for season in seasons):
                raise ValueError('Сначала вручную завершите действующий сезон')
            latest = seasons[0].id if seasons else 0
            if latest != previous_season_id:
                raise ValueError('Список сезонов изменился: обновите страницу')
            from app.services.preseason_service import PreseasonService
            preseason = PreseasonService()._parent(db, lock=True)
            if db.query(ClanWar.id).filter_by(status='active').first():
                raise ValueError('Сначала завершите оставшиеся битвы')
            from app.models.market import TradeCaravan
            if db.query(TradeCaravan.id).filter_by(status='traveling').first():
                raise ValueError('Дождитесь прибытия принятых караванов прежнего сезона')
            assignments = self._map(db, lock=True)
            active_clans = db.query(Clan).filter(Clan.is_deleted.is_(False), Clan.is_admin_clan.is_(False)).order_by(Clan.id).with_for_update().all()
            if preseason:
                # Дождаться текущих вступлений/верификаций до чтения их квитанций.
                from app.models.external_identity import ExternalPlayerIdentity
                db.query(ExternalPlayerIdentity).order_by(ExternalPlayerIdentity.id).with_for_update().all()
                CycleStartupService._members(db, now)
                PreseasonService()._qualifications(db, preseason, now, persist=True)
            valid_owners = {clan.id for clan in active_clans}
            for land, entry in assignments:
                land.is_playable, land.has_port = entry.is_playable, entry.has_port
                land.stronghold_power = max(1, land.stronghold_power or 0) if entry.fortress else 0
                land.influence_value = entry.influence_value
                if entry.profile_material:
                    land.resource_type = entry.profile_material
                    land.resource_output = int(getattr(entry.base, entry.profile_material))
                if not entry.is_playable or land.owner_clan_id not in valid_owners:
                    if land.owner_clan_id is not None:
                        for ownership in db.query(TerritoryOwnershipHistory).filter_by(territory_id=land.id, ended_at=None):
                            ownership.ended_at = now
                    land.owner_clan_id, land.owned_since = None, None
                land.status = 'active' if land.owner_clan_id else 'neutral'
            season = CampaignSeason(number=(db.query(func.max(CampaignSeason.number)).scalar() or 0) + 1,
                name=name, status='active', starting_influence=0, reset_development=False,
                starts_at=now, created_by_user_id=actor_user_id,
                rules_snapshot=dict(version=rules.version, rule_set_id=rules.id, values=dict(rules.values),
                    mechanics_version='cycle_v1', income_catalog_version=INCOME_CATALOG_VERSION,
                    launch_command_id=command_id, launch_previous_id=previous_season_id))
            db.add(season)
            if preseason:
                season.rules_snapshot = {**season.rules_snapshot, 'preseason_preparation_id': preseason.source_season_id}
            db.flush()
            cycle = CampaignCycleStore().start(db, season_id=season.id)
            db.flush()
            profiles = prepare_income_profiles(db, season_id=season.id, catalog_version=INCOME_CATALOG_VERSION, now=now, apply=True)
            startup = CycleStartupService()
            startup.initialize(db, cycle_id=cycle.id, now=now)
            for clan in active_clans:
                CycleEconomyStore().ensure_state(db, season_id=season.id, clan_id=clan.id)
                clan.base_influence = 0
            if preseason:
                PreseasonService().import_into(db, parent=preseason, season=season, cycle=cycle)
            db.flush()
            from app.services.cycle_ownership_service import CycleOwnershipService
            for clan in active_clans:
                CycleOwnershipService._recalculate(db, clan.id, cycle, rules, now)
            startup.qualify(db, cycle_id=cycle.id, now=now)
            result = dict(cycle_id=cycle.id, territories=len(profiles.profiles), clans=len(active_clans),
                          registration_hours=72, preparation_at=as_utc(cycle.preparation_at).isoformat())
            season.rules_snapshot = {**season.rules_snapshot, 'launch_result': result}
            AdminAuditService().record(db, actor_user_id=actor_user_id, action='cycle_season_started',
                entity_type='campaign_season', entity_id=season.id,
                after_data=dict(command_id=command_id, **result), reason='Ручной запуск нового сезона')
            db.flush()
            return self._result(season)
