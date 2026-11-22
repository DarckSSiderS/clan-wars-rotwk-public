from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from math import ceil

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.core.campaign_mode import (
    INTERSEASON_MESSAGE, cycle_owns_campaign, is_interseason, require_legacy_economy,
)
from app.core.exceptions import InsufficientPermissionsException
from app.core.permissions import ClanPermission, require_clan_permission
from app.core.time import as_utc, utc_now
from app.models.clan import Clan
from app.models.campaign import CampaignSeason
from app.models.market import MarketOffer, TradeCaravan
from app.models.territory import Territory
from app.models.user import User
from app.services.clan_economy_service import RESOURCE_FIELDS, ClanEconomyService
from app.services.campaign_rule_service import CampaignRuleService
from app.services.operation_service import ResourceLedgerService
from app.services.notification_service import notification_service


@dataclass
class MarketRoute:
    territories: list[Territory]
    modes: list[str]
    travel_steps: int

    @property
    def route_mode(self) -> str:
        unique_modes = set(self.modes)
        if unique_modes == {"sea"}:
            return "sea"
        if unique_modes == {"land"}:
            return "land"
        return "mixed"

    def payload(self) -> list[dict]:
        return [
            {
                "territory_id": territory.id,
                "name": territory.name,
                "via": self.modes[index - 1] if index > 0 else None,
            }
            for index, territory in enumerate(self.territories)
        ]


class ClanMarketService:
    def __init__(self):
        self.ledger = ResourceLedgerService()
        self.rule_service = CampaignRuleService()

    @staticmethod
    def lock_market(db: Session) -> None:
        """Serialize trading with clan archival and season transitions on PostgreSQL.

        Acquire before offer/clan row locks; release automatically on commit/rollback.
        SQLite serializes writes itself (and is used for local unit tests).
        """
        if db.get_bind().dialect.name == "postgresql":
            with db.no_autoflush:
                db.execute(text("SELECT pg_advisory_xact_lock(1129791826)"))

    @staticmethod
    def _active_season_id(db: Session) -> int | None:
        return db.query(CampaignSeason.id).filter(CampaignSeason.status == "active").scalar()

    def _cancel_offers(self, db: Session, offers, reason: str) -> None:
        clan_ids = {
            clan_id for offer in offers
            for clan_id in (offer.creator_clan_id, offer.accepted_by_clan_id)
            if clan_id is not None
        }
        clans = self.ledger.lock_clans(db, clan_ids)
        for offer in offers:
            if offer.status == "in_transit":
                self._fail_and_refund(
                    db, offer, clans.get(offer.creator_clan_id),
                    clans.get(offer.accepted_by_clan_id), reason,
                )
            elif offer.status == "open":
                offer.status = "canceled"
                offer.canceled_at = utc_now()
                offer.failure_reason = reason

    def cancel_for_clan(self, db: Session, clan_id: int) -> None:
        self.lock_market(db)
        offers = db.query(MarketOffer).filter(
            MarketOffer.status.in_(["open", "in_transit"]),
            or_(MarketOffer.creator_clan_id == clan_id, MarketOffer.accepted_by_clan_id == clan_id),
        ).order_by(MarketOffer.id).with_for_update().populate_existing().all()
        self._cancel_offers(db, offers, "Клан расформирован")
        self.ledger.lock_clans(db, [clan_id])

    def cancel_for_season_reset(self, db: Session) -> None:
        self.lock_market(db)
        # A stable order also prevents a worker holding clan A while a reset holds B.
        self.ledger.lock_clans(db, [row[0] for row in db.query(Clan.id).all()])
        offers = db.query(MarketOffer).filter(
            MarketOffer.status.in_(["open", "in_transit"]),
        ).order_by(MarketOffer.id).with_for_update().populate_existing().all()
        self._cancel_offers(db, offers, "Сезон завершён")
        db.flush()

    def create_offer(
        self,
        db: Session,
        *,
        creator_clan_id: int,
        give_resource: str,
        give_amount: int,
        receive_resource: str,
        receive_amount: int,
        expires_in_days: int,
        current_user: User,
    ) -> dict:
        self.lock_market(db)
        require_legacy_economy(db)
        rules = self.rule_service.get_active(db).values
        clan, _ = require_clan_permission(
            db,
            creator_clan_id,
            current_user,
            ClanPermission.MANAGE_MARKET,
        )
        self._validate_resources(
            give_resource,
            give_amount,
            receive_resource,
            receive_amount,
        )
        self._require_map_presence(db, clan.id)
        ClanEconomyService().settle_clan(db, clan, rules=rules)
        if int(getattr(clan, give_resource) or 0) < give_amount:
            raise InsufficientPermissionsException(
                "У клана не хватает ресурса для этого предложения"
            )

        now = utc_now()
        offer = MarketOffer(
            season_id=self._active_season_id(db),
            creator_clan_id=clan.id,
            created_by_user_id=current_user.id,
            give_resource=give_resource,
            give_amount=give_amount,
            receive_resource=receive_resource,
            receive_amount=receive_amount,
            status="open",
            expires_at=now + timedelta(days=expires_in_days),
        )
        db.add(offer)
        db.commit()
        db.refresh(offer)
        return self.serialize(offer)

    def list_market(self, db: Session, clan_id: int | None = None) -> dict:
        rules = self.rule_service.get_active(db).values
        self.settle_due(db)
        self.expire_open_offers(db)
        offers = (
            db.query(MarketOffer)
            .order_by(MarketOffer.created_at.desc())
            .limit(200)
            .all()
        )
        public_offers = []
        for offer in offers:
            if offer.status != "open":
                continue
            quote = None
            if clan_id and offer.creator_clan_id != clan_id:
                quote = self.quote_for_clan(db, offer, clan_id, rules=rules)
            public_offers.append(self.serialize(offer, quote=quote))
        clan_offers = [
            self.serialize(offer)
            for offer in offers
            if clan_id and (
                offer.creator_clan_id == clan_id
                or offer.accepted_by_clan_id == clan_id
            )
        ]
        active_caravans = (
            db.query(TradeCaravan)
            .filter(TradeCaravan.status == "traveling")
            .order_by(TradeCaravan.eta.asc())
            .all()
        )
        return {
            "offers": public_offers,
            "clan_activity": clan_offers,
            "caravans": [
                self.serialize_caravan(caravan)
                for caravan in active_caravans
                if not clan_id
                or caravan.from_clan_id == clan_id
                or caravan.to_clan_id == clan_id
            ],
        }

    def quote_for_clan(
        self,
        db: Session,
        offer: MarketOffer,
        accepter_clan_id: int,
        *,
        rules: Mapping[str, int | float] | None = None,
    ) -> dict:
        if is_interseason(db):
            return {
                'available': False,
                'reason_code': 'interseason',
                'reason': INTERSEASON_MESSAGE,
            }
        if cycle_owns_campaign(db):
            return {
                'available': False,
                'reason_code': 'cycle_campaign',
                'reason': 'Legacy trading is unavailable in a cycle_v1 campaign',
            }
        if rules is None:
            rules = self.rule_service.get_active(db).values
        if not db.query(Territory.id).filter(
            Territory.owner_clan_id == accepter_clan_id
        ).first():
            return {
                "available": False,
                "reason_code": "accepter_has_no_territory",
                "reason": "У вашего клана нет территории на карте",
            }
        route = self._best_route_between_clans(
            db,
            offer.creator_clan_id,
            accepter_clan_id,
        )
        if not route:
            return {
                "available": False,
                "reason_code": "no_delivery_route",
                "reason": (
                    "Между владениями нет сухопутного пути, "
                    "а для морской доставки оба клана должны владеть портом"
                ),
            }
        steps = route.travel_steps
        travel_hours = self.travel_hours(route, rules)
        return {
            "available": True,
            "route": route.payload(),
            "route_mode": route.route_mode,
            "route_steps": steps,
            "travel_hours": travel_hours,
            "estimated_arrival_at": utc_now() + timedelta(hours=travel_hours),
            "creator_shipping_cost": self.shipping_cost(
                steps,
                offer.give_amount,
                rules,
            ),
            "accepter_shipping_cost": self.shipping_cost(
                steps,
                offer.receive_amount,
                rules,
            ),
        }

    def accept_offer(
        self,
        db: Session,
        *,
        offer_id: int,
        accepter_clan_id: int,
        current_user: User,
    ) -> dict:
        self.lock_market(db)
        require_legacy_economy(db)
        accepter, _ = require_clan_permission(
            db,
            accepter_clan_id,
            current_user,
            ClanPermission.MANAGE_MARKET,
        )
        offer = (
            db.query(MarketOffer)
            .filter(MarketOffer.id == offer_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
        if not offer:
            raise InsufficientPermissionsException("Предложение не найдено")
        now = utc_now()
        if offer.status != "open":
            raise InsufficientPermissionsException(
                "Это предложение уже недоступно"
            )
        if offer.season_id != self._active_season_id(db):
            raise InsufficientPermissionsException("Предложение относится к другому сезону")
        if as_utc(offer.expires_at) <= now:
            offer.status = "expired"
            db.commit()
            raise InsufficientPermissionsException("Срок предложения истек")
        if offer.creator_clan_id == accepter.id:
            raise InsufficientPermissionsException(
                "Нельзя принять предложение своего клана"
            )

        clans = self.ledger.lock_clans(db, [offer.creator_clan_id, accepter.id])
        creator = clans.get(offer.creator_clan_id)
        if creator is None or creator.is_deleted or accepter.is_deleted:
            raise InsufficientPermissionsException("Клан продавца не найден")
        rules = self.rule_service.get_active(db).values
        self._require_map_presence(db, creator.id)
        self._require_map_presence(db, accepter.id)
        economy = ClanEconomyService()
        economy.settle_clan(db, creator, rules=rules)
        economy.settle_clan(db, accepter, rules=rules)

        route = self._best_route_between_clans(db, creator.id, accepter.id)
        if not route:
            raise InsufficientPermissionsException(
                "Между владениями нет сухопутного пути, а для морской доставки оба клана должны владеть портом"
            )
        steps = route.travel_steps
        creator_shipping = self.shipping_cost(steps, offer.give_amount, rules)
        accepter_shipping = self.shipping_cost(steps, offer.receive_amount, rules)
        self._check_cargo_and_gold(
            creator,
            offer.give_resource,
            offer.give_amount,
            creator_shipping,
        )
        self._check_cargo_and_gold(
            accepter,
            offer.receive_resource,
            offer.receive_amount,
            accepter_shipping,
        )

        route_payload = route.payload()
        eta = now + timedelta(hours=self.travel_hours(route, rules))
        offer.accepted_by_clan_id = accepter.id
        offer.accepted_by_user_id = current_user.id
        offer.status = "in_transit"
        offer.route = route_payload
        offer.route_steps = steps
        offer.creator_shipping_cost = creator_shipping
        offer.accepter_shipping_cost = accepter_shipping
        offer.accepted_at = now
        offer.eta = eta

        self._reserve_cargo(
            db,
            offer,
            clan=creator,
            resource=offer.give_resource,
            amount=offer.give_amount,
            shipping=creator_shipping,
            actor_user_id=current_user.id,
            side="creator",
        )
        self._reserve_cargo(
            db,
            offer,
            clan=accepter,
            resource=offer.receive_resource,
            amount=offer.receive_amount,
            shipping=accepter_shipping,
            actor_user_id=current_user.id,
            side="accepter",
        )

        db.add_all(
            [
                TradeCaravan(
                    offer_id=offer.id,
                    from_clan_id=creator.id,
                    to_clan_id=accepter.id,
                    resource=offer.give_resource,
                    amount=offer.give_amount,
                    status="traveling",
                    route=route_payload,
                    departed_at=now,
                    eta=eta,
                ),
                TradeCaravan(
                    offer_id=offer.id,
                    from_clan_id=accepter.id,
                    to_clan_id=creator.id,
                    resource=offer.receive_resource,
                    amount=offer.receive_amount,
                    status="traveling",
                    route=self._reverse_route_payload(route_payload),
                    departed_at=now,
                    eta=eta,
                ),
            ]
        )
        for clan in (creator, accepter):
            notification_service.create_for_clan(
                db,
                clan_id=clan.id,
                notification_type="clan_trade_started",
                title="Караваны отправлены",
                message=(
                    f"Сделка между «{creator.name}» и «{accepter.name}» принята. "
                    f"Ожидаемое прибытие: {eta.isoformat()}."
                ),
                link_url=f"/clans/{clan.id}",
                entity_type="market_offer",
                entity_id=offer.id,
                commit=False,
            )
        db.commit()
        db.refresh(offer)
        return self.serialize(offer)

    def cancel_offer(
        self,
        db: Session,
        *,
        offer_id: int,
        current_user: User,
    ) -> dict:
        self.lock_market(db)
        require_legacy_economy(db)
        offer = db.query(MarketOffer).filter_by(id=offer_id).with_for_update().populate_existing().first()
        if not offer:
            raise InsufficientPermissionsException("Предложение не найдено")
        require_clan_permission(
            db,
            offer.creator_clan_id,
            current_user,
            ClanPermission.MANAGE_MARKET,
        )
        if offer.status != "open":
            raise InsufficientPermissionsException(
                "Отменить можно только открытое предложение"
            )
        offer.status = "canceled"
        offer.canceled_at = utc_now()
        db.commit()
        return self.serialize(offer)

    def settle_due(self, db: Session) -> int:
        self.lock_market(db)
        now = utc_now()
        season_id = self._active_season_id(db)
        # With no replacement season, balances were not reset: escrow still arrives at ETA.
        offers = (
            db.query(MarketOffer)
            .filter(
                MarketOffer.status == "in_transit",
                or_(MarketOffer.eta <= now,
                    MarketOffer.season_id != season_id if season_id is not None
                    else False,
                    MarketOffer.season_id.is_(None) if season_id is not None else False),
            )
            .order_by(MarketOffer.id)
            .with_for_update()
            .populate_existing()
            .all()
        )
        clans = self.ledger.lock_clans(db, [
            clan_id for offer in offers
            for clan_id in (offer.creator_clan_id, offer.accepted_by_clan_id)
        ])
        completed = 0
        for offer in offers:
            creator = clans.get(offer.creator_clan_id)
            accepter = clans.get(offer.accepted_by_clan_id)
            if season_id is not None and offer.season_id != season_id:
                # Never credit a prior season's escrow into freshly reset balances.
                offer.status = "failed"
                offer.failure_reason = "Караван относится к другому сезону"
                offer.canceled_at = now
                for caravan in offer.caravans:
                    caravan.status = "failed"
                continue
            if not creator or not accepter or creator.is_deleted or accepter.is_deleted:
                self._fail_and_refund(
                    db,
                    offer,
                    creator,
                    accepter,
                    "Один из кланов больше не существует",
                )
                continue

            delivery_id = f"market-delivery:{offer.id}"
            self.ledger.apply_change(
                db,
                accepter,
                resource=offer.give_resource,
                amount=offer.give_amount,
                operation_id=delivery_id,
                action="market_delivery",
                source_type="market_offer",
                source_id=offer.id,
            )
            self.ledger.apply_change(
                db,
                creator,
                resource=offer.receive_resource,
                amount=offer.receive_amount,
                operation_id=delivery_id,
                action="market_delivery",
                source_type="market_offer",
                source_id=offer.id,
            )
            offer.status = "completed"
            offer.completed_at = now
            for caravan in offer.caravans:
                caravan.status = "delivered"
                caravan.arrived_at = now
            for clan in (creator, accepter):
                notification_service.create_for_clan(
                    db,
                    clan_id=clan.id,
                    notification_type="clan_trade_completed",
                    title="Караваны прибыли",
                    message=(
                        f"Сделка между «{creator.name}» и «{accepter.name}» завершена, "
                        "ресурсы зачислены в казну."
                    ),
                    link_url=f"/clans/{clan.id}",
                    entity_type="market_offer",
                    entity_id=offer.id,
                    commit=False,
                )
            completed += 1
        if offers:
            db.commit()
        return completed

    def expire_open_offers(self, db: Session) -> int:
        if is_interseason(db):
            return 0
        self.lock_market(db)
        now = utc_now()
        expired = (
            db.query(MarketOffer)
            .filter(
                MarketOffer.status == "open",
                MarketOffer.expires_at <= now,
            )
            .update(
                {MarketOffer.status: "expired"},
                synchronize_session=False,
            )
        )
        if expired:
            db.commit()
        return expired

    @staticmethod
    def shipping_cost(
        steps: int,
        amount: int,
        rules: Mapping[str, int | float],
    ) -> int:
        base_shipping_cost = max(
            int(rules["CARAVAN_MIN_GOLD_FEE"]),
            int(rules["CARAVAN_BASE_GOLD_FEE"])
            + steps * int(rules["CARAVAN_DISTANCE_GOLD_FEE"])
            + ceil(amount / int(rules["CARAVAN_VOLUME_STEP"]))
            * int(rules["CARAVAN_VOLUME_GOLD_FEE"]),
        )
        return ceil(
            base_shipping_cost
            * int(rules["CARAVAN_GOLD_FEE_MULTIPLIER_PERCENT"])
            / 100
        )

    @staticmethod
    def travel_hours(
        route: MarketRoute,
        rules: Mapping[str, int | float],
    ) -> int:
        hours_per_step = (
            int(rules["CARAVAN_SEA_HOURS_PER_STEP"])
            if route.route_mode == "sea"
            else int(rules["CARAVAN_HOURS_PER_STEP"])
        )
        return route.travel_steps * hours_per_step

    def _reserve_cargo(
        self,
        db: Session,
        offer: MarketOffer,
        *,
        clan: Clan,
        resource: str,
        amount: int,
        shipping: int,
        actor_user_id: int,
        side: str,
    ) -> None:
        self.ledger.apply_change(
            db,
            clan,
            resource=resource,
            amount=-amount,
            operation_id=f"market-escrow:{offer.id}:{side}",
            action="market_cargo_reserved",
            source_type="market_offer",
            source_id=offer.id,
            actor_user_id=actor_user_id,
        )
        self.ledger.apply_change(
            db,
            clan,
            resource="gold",
            amount=-shipping,
            operation_id=f"market-shipping:{offer.id}:{side}",
            action="market_shipping_paid",
            source_type="market_offer",
            source_id=offer.id,
            actor_user_id=actor_user_id,
            details={"route_steps": offer.route_steps},
        )

    def _fail_and_refund(
        self,
        db: Session,
        offer: MarketOffer,
        creator: Clan | None,
        accepter: Clan | None,
        reason: str,
    ) -> None:
        if creator:
            self.ledger.apply_change(
                db,
                creator,
                resource=offer.give_resource,
                amount=offer.give_amount,
                operation_id=f"market-refund:{offer.id}:creator",
                action="market_cargo_refunded",
                source_type="market_offer",
                source_id=offer.id,
            )
        if accepter:
            self.ledger.apply_change(
                db,
                accepter,
                resource=offer.receive_resource,
                amount=offer.receive_amount,
                operation_id=f"market-refund:{offer.id}:accepter",
                action="market_cargo_refunded",
                source_type="market_offer",
                source_id=offer.id,
            )
        offer.status = "failed"
        offer.failure_reason = reason
        offer.completed_at = utc_now()
        for caravan in offer.caravans:
            caravan.status = "failed"

    def _validate_resources(
        self,
        give_resource: str,
        give_amount: int,
        receive_resource: str,
        receive_amount: int,
    ) -> None:
        if give_resource not in RESOURCE_FIELDS or receive_resource not in RESOURCE_FIELDS:
            raise InsufficientPermissionsException("Неизвестный ресурс")
        if give_resource == receive_resource:
            raise InsufficientPermissionsException(
                "Для обмена выберите разные ресурсы"
            )
        if give_amount <= 0 or receive_amount <= 0:
            raise InsufficientPermissionsException(
                "Количество ресурса должно быть больше нуля"
            )

    def _require_map_presence(self, db: Session, clan_id: int) -> None:
        has_territory = (
            db.query(Territory.id)
            .filter(Territory.owner_clan_id == clan_id)
            .first()
        )
        if not has_territory:
            raise InsufficientPermissionsException(
                "Рынок доступен только кланам с территорией на карте"
            )

    def _check_cargo_and_gold(
        self,
        clan: Clan,
        resource: str,
        amount: int,
        shipping: int,
    ) -> None:
        resource_balance = int(getattr(clan, resource) or 0)
        required_resource = amount + shipping if resource == "gold" else amount
        if resource_balance < required_resource:
            raise InsufficientPermissionsException(
                f"Клану «{clan.name}» не хватает груза"
            )
        if resource != "gold" and int(clan.gold or 0) < shipping:
            raise InsufficientPermissionsException(
                f"Клану «{clan.name}» не хватает золота на доставку"
            )

    def _best_route_between_clans(
        self,
        db: Session,
        first_clan_id: int,
        second_clan_id: int,
    ) -> MarketRoute | None:
        territories = db.query(Territory).filter(Territory.is_playable.is_(True)).all()
        by_id = {territory.id: territory for territory in territories}
        starts = {
            territory.id
            for territory in territories
            if territory.owner_clan_id == first_clan_id
        }
        targets = {
            territory.id
            for territory in territories
            if territory.owner_clan_id == second_clan_id
        }
        land_route = self._land_route(by_id, starts, targets)
        first_ports = [
            territory
            for territory in territories
            if territory.owner_clan_id == first_clan_id and territory.has_port
        ]
        second_ports = [
            territory
            for territory in territories
            if territory.owner_clan_id == second_clan_id and territory.has_port
        ]
        sea_route = None
        if first_ports and second_ports:
            sea_route = MarketRoute(
                territories=[first_ports[0], second_ports[0]],
                modes=["sea"],
                travel_steps=2,
            )
        if land_route and sea_route:
            return min(
                (land_route, sea_route),
                key=lambda route: (
                    route.travel_steps,
                    0 if route.route_mode == "land" else 1,
                ),
            )
        return land_route or sea_route

    def _land_route(
        self,
        by_id: dict[int, Territory],
        starts: set[int],
        targets: set[int],
    ) -> MarketRoute | None:
        queue = deque(starts)
        previous = {territory_id: None for territory_id in starts}
        found = None
        while queue:
            current = queue.popleft()
            if current in targets:
                found = current
                break
            for neighbor in by_id[current].adjacent_territory_ids or []:
                try:
                    neighbor_id = int(neighbor)
                except (TypeError, ValueError):
                    continue
                if neighbor_id not in by_id or neighbor_id in previous:
                    continue
                previous[neighbor_id] = current
                queue.append(neighbor_id)
        if found is None:
            return None
        route_ids = []
        cursor = found
        while cursor is not None:
            route_ids.append(cursor)
            cursor = previous[cursor]
        route_ids.reverse()
        return MarketRoute(
            territories=[by_id[territory_id] for territory_id in route_ids],
            modes=["land"] * max(0, len(route_ids) - 1),
            travel_steps=max(1, len(route_ids) - 1),
        )

    @staticmethod
    def _reverse_route_payload(route: list[dict]) -> list[dict]:
        if not route:
            return []
        reversed_territories = list(reversed(route))
        reversed_modes = list(reversed([step.get("via") for step in route[1:]]))
        return [
            {
                **territory,
                "via": reversed_modes[index - 1] if index > 0 else None,
            }
            for index, territory in enumerate(reversed_territories)
        ]

    def serialize(self, offer: MarketOffer, quote: dict | None = None) -> dict:
        route_modes = {
            step.get("via")
            for step in (offer.route or [])[1:]
            if step.get("via")
        }
        route_mode = (
            next(iter(route_modes))
            if len(route_modes) == 1
            else "mixed" if route_modes
            else "land" if len(offer.route or []) > 1
            else None
        )
        payload = {
            "id": offer.id,
            "creator_clan_id": offer.creator_clan_id,
            "creator_clan_name": (
                offer.creator_clan.name if offer.creator_clan else None
            ),
            "accepted_by_clan_id": offer.accepted_by_clan_id,
            "accepted_by_clan_name": (
                offer.accepted_by_clan.name if offer.accepted_by_clan else None
            ),
            "give_resource": offer.give_resource,
            "give_amount": offer.give_amount,
            "receive_resource": offer.receive_resource,
            "receive_amount": offer.receive_amount,
            "status": offer.status,
            "route": offer.route or [],
            "route_mode": route_mode,
            "route_steps": offer.route_steps,
            "creator_shipping_cost": offer.creator_shipping_cost,
            "accepter_shipping_cost": offer.accepter_shipping_cost,
            "expires_at": offer.expires_at,
            "accepted_at": offer.accepted_at,
            "eta": offer.eta,
            "completed_at": offer.completed_at,
            "failure_reason": offer.failure_reason,
            "created_at": offer.created_at,
        }
        if quote is not None:
            payload["quote"] = quote
        return payload

    def serialize_caravan(self, caravan: TradeCaravan) -> dict:
        now = utc_now()
        departed = as_utc(caravan.departed_at)
        eta = as_utc(caravan.eta)
        total = max(1.0, (eta - departed).total_seconds())
        elapsed = max(0.0, min(total, (now - departed).total_seconds()))
        remaining = max(0, round((eta - now).total_seconds()))
        route_modes = {
            step.get("via")
            for step in (caravan.route or [])[1:]
            if step.get("via")
        }
        route_mode = (
            next(iter(route_modes))
            if len(route_modes) == 1
            else "mixed" if route_modes
            else "land" if len(caravan.route or []) > 1
            else None
        )
        return {
            "id": caravan.id,
            "offer_id": caravan.offer_id,
            "from_clan_id": caravan.from_clan_id,
            "from_clan_name": caravan.from_clan.name if caravan.from_clan else None,
            "to_clan_id": caravan.to_clan_id,
            "to_clan_name": caravan.to_clan.name if caravan.to_clan else None,
            "resource": caravan.resource,
            "amount": caravan.amount,
            "status": caravan.status,
            "route": caravan.route or [],
            "route_mode": route_mode,
            "departed_at": caravan.departed_at,
            "eta": caravan.eta,
            "arrived_at": caravan.arrived_at,
            "progress_percent": round(elapsed / total * 100, 1),
            "remaining_seconds": remaining,
        }
