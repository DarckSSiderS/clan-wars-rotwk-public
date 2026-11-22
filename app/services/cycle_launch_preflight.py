"""Пробная подготовка циклов и доходов с обязательным откатом всех записей.

Доверенный инструмент приёмки вызывает её только на изолированной копии базы.
Публичного метода запуска сезона или изменения рабочей кампании здесь нет.
"""

from datetime import datetime

from sqlalchemy import func

from app.models.campaign import CampaignSeason
from app.models.clan import Clan
from app.models.territory import Territory
from app.services.campaign_cycle_service import _utc
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.campaign_rule_service import CampaignRuleService
from app.services.cycle_economy import Resources
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_income_catalog import INCOME_CATALOG_VERSION, prepare_income_profiles
from app.services.cycle_startup_service import CycleStartupService


def preview_preparation(db, *, now: datetime):
    now = _utc(now)
    if db.new or db.dirty or db.deleted:
        raise ValueError('Перед репетицией нужно явно сохранить изменения сессии через flush')
    if db.query(CampaignSeason.id).filter_by(status='active').first():
        raise ValueError('Прежний активный сезон должен быть завершён владельцем вручную; репетиция его не останавливает')
    with CycleEconomyStore._atomic(db):
        trial = db.begin_nested()
        try:
            rule = CampaignRuleService().get_active(db)
            season = CampaignSeason(number=(db.query(func.max(CampaignSeason.number)).scalar() or 0) + 1,
                name='Изолированная репетиция нового режима', starts_at=now, status='active',
                rules_snapshot=dict(version=rule.version, rule_set_id=rule.id, values=dict(rule.values),
                    mechanics_version='cycle_v1', income_catalog_version=INCOME_CATALOG_VERSION))
            db.add(season)
            adjustments = []
            island = db.query(Territory).filter_by(name='Тол-Фалас').one_or_none()
            if island is not None and island.is_playable:
                island.is_playable = False
                adjustments.append(dict(name=island.name, is_playable=False))
                if island.has_port:
                    island.has_port = False
                    adjustments[-1]['has_port'] = False
            db.flush()
            cycle = CampaignCycleStore().start(db, season_id=season.id)
            db.flush()
            profiles = prepare_income_profiles(db, season_id=season.id,
                catalog_version=INCOME_CATALOG_VERSION, now=now, apply=True)
            CycleStartupService().initialize(db, cycle_id=cycle.id, now=now)
            clans = db.query(Clan).filter(Clan.is_deleted.is_(False), Clan.is_admin_clan.is_(False)).all()
            for clan in clans:
                CycleEconomyStore().ensure_state(db, season_id=season.id, clan_id=clan.id)
            qualified = CycleStartupService().qualify(db, cycle_id=cycle.id, now=now)
            total = Resources()
            for _, entry in profiles.profiles:
                total += entry.base
            timeline = CampaignCycleStore.timeline(cycle)
            return dict(catalog_version=INCOME_CATALOG_VERSION, income_profiles=len(profiles.profiles),
                playable_territories=db.query(Territory).filter_by(is_playable=True).count(),
                active_clans=len(clans), qualified_gift_slots=len(qualified),
                registration_hours=int((timeline.preparation_at - now).total_seconds() / 3600),
                territory_daily_totals={key: str(getattr(total, key)) for key in ('gold', 'iron', 'wood', 'food', 'mithril')},
                map_adjustments=adjustments, changes_rolled_back=True)
        finally:
            trial.rollback()
            db.expire_all()
