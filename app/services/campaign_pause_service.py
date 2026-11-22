from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.campaign_mode import INTERSEASON_MESSAGE, is_interseason
from app.core.time import as_utc, utc_now
from app.models.campaign import CampaignSettings
from app.models.clan import Clan
from app.models.clan_warfare import ClanAttackPointSpend
from app.models.market import MarketOffer, TradeCaravan
from app.models.territory import Territory
from app.models.war import ClanWar
from app.services.campaign_settings_service import CampaignSettingsService
from app.services.operation_service import AdminAuditService


class CampaignPauseService:
    def __init__(self) -> None:
        self.settings = CampaignSettingsService()
        self.audit = AdminAuditService()

    @staticmethod
    def is_paused(db: Session) -> bool:
        """Effective seasonal stop; interseason never writes a pause calendar."""
        campaign = db.get(CampaignSettings, CampaignSettingsService.SETTINGS_ID)
        return bool(campaign and campaign.is_paused) or is_interseason(db)

    def _locked_settings(self, db: Session) -> CampaignSettings:
        self.settings.get_or_create(db)
        return (
            db.query(CampaignSettings)
            .filter(CampaignSettings.id == CampaignSettingsService.SETTINGS_ID)
            .with_for_update()
            .one()
        )

    def pause(
        self,
        db: Session,
        *,
        actor_user_id: int,
        reason: str,
        now: datetime | None = None,
    ) -> CampaignSettings:
        from app.core.campaign_mode import cycle_owns_campaign
        if is_interseason(db):
            raise ValueError(INTERSEASON_MESSAGE)
        if cycle_owns_campaign(db):
            raise ValueError('Старая пауза не поддерживает циклы новой кампании')
        campaign = self._locked_settings(db)
        if campaign.is_paused:
            return campaign

        paused_at = as_utc(now) or utc_now()
        campaign.is_paused = True
        campaign.paused_at = paused_at
        campaign.paused_by_user_id = actor_user_id
        campaign.pause_reason = reason.strip()[:500]
        self.audit.record(
            db,
            actor_user_id=actor_user_id,
            action="campaign_paused",
            entity_type="campaign_settings",
            entity_id=campaign.id,
            before_data={"is_paused": False},
            after_data={"is_paused": True, "paused_at": paused_at.isoformat()},
            reason=campaign.pause_reason,
        )
        db.commit()
        db.refresh(campaign)
        return campaign
    @staticmethod
    def _shift(value: datetime | None, duration: timedelta) -> datetime | None:
        return as_utc(value) + duration if value is not None else None

    def _shift_deadlines(
        self,
        db: Session,
        *,
        paused_at: datetime,
        duration: timedelta,
    ) -> dict[str, int]:
        shifted = {
            "wars": 0,
            "attack_points": 0,
            "clans": 0,
            "territories": 0,
            "offers": 0,
            "caravans": 0,
        }
        for war in db.query(ClanWar).filter(ClanWar.status == "active").all():
            if war.ends_at is not None:
                war.ends_at = self._shift(war.ends_at, duration)
                shifted["wars"] += 1

        spends = db.query(ClanAttackPointSpend).filter(
            ClanAttackPointSpend.refunded_at.is_(None)
        ).all()
        for spend in spends:
            if as_utc(spend.recover_at) > paused_at:
                spend.recover_at = self._shift(spend.recover_at, duration)
                shifted["attack_points"] += 1

        for clan in db.query(Clan).all():
            changed = False
            if clan.last_economy_tick is not None:
                clan.last_economy_tick = self._shift(clan.last_economy_tick, duration)
                changed = True
            if clan.next_attack_at is not None and as_utc(clan.next_attack_at) > paused_at:
                clan.next_attack_at = self._shift(clan.next_attack_at, duration)
                changed = True
            if changed:
                shifted["clans"] += 1

        territories = db.query(Territory).filter(
            (Territory.resource_income_ready_at.isnot(None))
            | (Territory.last_resource_payout_at.isnot(None))
            | (Territory.last_weekly_payout_at.isnot(None))
        ).all()
        for territory in territories:
            territory.resource_income_ready_at = self._shift(
                territory.resource_income_ready_at,
                duration,
            )
            territory.last_resource_payout_at = self._shift(
                territory.last_resource_payout_at,
                duration,
            )
            territory.last_weekly_payout_at = self._shift(
                territory.last_weekly_payout_at,
                duration,
            )
            shifted["territories"] += 1

        offers = db.query(MarketOffer).filter(
            MarketOffer.status.in_(("open", "in_transit"))
        ).all()
        for offer in offers:
            changed = False
            if offer.status == "open" and offer.expires_at is not None:
                offer.expires_at = self._shift(offer.expires_at, duration)
                changed = True
            if offer.status == "in_transit" and offer.eta is not None:
                offer.eta = self._shift(offer.eta, duration)
                changed = True
            if changed:
                shifted["offers"] += 1

        caravans = db.query(TradeCaravan).filter(
            TradeCaravan.status == "traveling"
        ).all()
        for caravan in caravans:
            caravan.eta = self._shift(caravan.eta, duration)
            shifted["caravans"] += 1
        return shifted

    def resume(
        self,
        db: Session,
        *,
        actor_user_id: int,
        reason: str,
        now: datetime | None = None,
    ) -> CampaignSettings:
        if is_interseason(db):
            raise ValueError(INTERSEASON_MESSAGE)
        campaign = self._locked_settings(db)
        if not campaign.is_paused:
            return campaign

        resumed_at = as_utc(now) or utc_now()
        paused_at = as_utc(campaign.paused_at) or resumed_at
        duration = max(timedelta(0), resumed_at - paused_at)
        shifted = self._shift_deadlines(
            db,
            paused_at=paused_at,
            duration=duration,
        )
        previous_reason = campaign.pause_reason
        campaign.is_paused = False
        campaign.paused_at = None
        campaign.paused_by_user_id = None
        campaign.pause_reason = None
        self.audit.record(
            db,
            actor_user_id=actor_user_id,
            action="campaign_resumed",
            entity_type="campaign_settings",
            entity_id=campaign.id,
            before_data={
                "is_paused": True,
                "paused_at": paused_at.isoformat(),
                "pause_reason": previous_reason,
            },
            after_data={
                "is_paused": False,
                "resumed_at": resumed_at.isoformat(),
                "paused_seconds": int(duration.total_seconds()),
                "shifted": shifted,
            },
            reason=reason.strip()[:500],
        )
        db.commit()
        db.refresh(campaign)
        return campaign
