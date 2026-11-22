"""Caller-owned transactions; cycle -> season -> offer -> sorted wallets.

The parent must invoke cancel_hostile_pair in the war transaction and expire
at settlement. Neither hook touches public offers or accepted transit on war.
No legacy wallet, shipping charge, grant recreation, commit or network access.
"""

from datetime import timedelta
from contextlib import contextmanager

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.cycle_diplomacy import CycleDiplomacyPair
from app.models.cycle_economy import CycleEconomyState
from app.models.cycle_market import CycleMarketOffer, CycleMarketCaravan, CycleMarketCommand
from app.models.territory import Territory
from app.services import cycle_economy as rules
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.campaign_cycle_service import CyclePhase, _utc
from app.services.campaign_rule_service import CampaignRuleService
from app.services.cycle_diplomacy_service import first_full_cycle, _active, _cursor
from app.services.cycle_economy_store import CycleEconomyStore, EconomyConflict
from app.services.market_service import ClanMarketService


class CycleMarketService:
    economy = CycleEconomyStore()

    @contextmanager
    def _atomic(self, db):
        try:
            with self.economy._atomic(db):
                yield
        except Exception:
            # Economy CAS uses Core UPDATE + refresh; savepoint rollback alone
            # does not expire those refreshed, ORM-clean identity-map entries.
            db.expire_all()
            raise

    def _context(self, db, cycle_id, now, manual=True):
        cycle = CampaignCycleStore()._locked(db, cycle_id)
        season = db.query(CampaignSeason).filter_by(id=cycle.season_id).with_for_update().populate_existing().one()
        if (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
            raise ValueError('Season must explicitly enable cycle_v1')
        if manual and season.status != 'active':
            raise ValueError('Active season required')
        if db.query(CampaignCycleRecord.id).filter(
                CampaignCycleRecord.season_id == season.id, CampaignCycleRecord.number > cycle.number).first():
            raise ValueError('Latest cycle required')
        now = _utc(now)
        phase = CampaignCycleStore.timeline(cycle).phase_at(now)
        if manual and phase == CyclePhase.SEASON_ENDED:
            raise ValueError('Trading is closed after the final cycle')
        return cycle, phase, now

    @staticmethod
    def _revision(row, expected):
        if type(expected) is not int or expected != row.revision:
            raise EconomyConflict('Market or wallet revision changed')

    @staticmethod
    def _cargo(value):
        cargo = value if isinstance(value, rules.Resources) else rules.Resources(**value)
        rules.barter_fee(cargo)
        return cargo

    @staticmethod
    def _json(cargo):
        return {key: str(getattr(cargo, key)) for key in rules.MATERIALS}

    @staticmethod
    def _receipt(db, season_id, command_id, payload, result=None):
        if not isinstance(command_id, str) or not command_id.strip() or len(command_id) > 128:
            raise ValueError('Nonempty command ID of at most 128 characters required')
        row = db.query(CycleMarketCommand).filter_by(season_id=season_id, command_id=command_id).one_or_none()
        if row:
            if row.payload != payload:
                raise ValueError('Command ID reused with different terms')
            return row.result
        if result is not None:
            db.add(CycleMarketCommand(season_id=season_id, command_id=command_id, payload=payload, result=result))
            db.flush()
        return None

    @staticmethod
    def _wallets(db, season_id, *clans):
        rows = db.query(CycleEconomyState).filter(
            CycleEconomyState.season_id == season_id, CycleEconomyState.clan_id.in_(clans)
        ).order_by(CycleEconomyState.clan_id).with_for_update().populate_existing().all()
        if len(rows) != len(set(clans)):
            raise ValueError('Existing seasonal wallets required; no implicit starter grants')
        return {row.clan_id: row for row in rows}

    @staticmethod
    def _hostile(db, cycle, first, second, now):
        pair = db.query(CycleDiplomacyPair).filter_by(season_id=cycle.season_id,
            clan_low_id=min(first, second), clan_high_id=max(first, second)).populate_existing().one_or_none()
        return bool(_active(pair, _cursor(cycle, now)))

    @staticmethod
    def _land(db, clan):
        if not db.query(Territory.id).filter(Territory.owner_clan_id == clan,
                                             Territory.is_playable.is_(True)).first():
            raise ValueError('Playable land required')

    def _route(self, db, first, second):
        route = ClanMarketService()._best_route_between_clans(db, first, second)
        if route is None:
            raise ValueError('No eligible land/port route')
        return route

    def create(self, db, *, cycle_id, clan_id, actor_id, offered, requested, now,
               command_id, expected_wallet_revision, target_clan_id=None):
        offered, requested = self._cargo(offered), self._cargo(requested)
        payload = dict(kind='create', clan=clan_id, actor=actor_id, target=target_clan_id,
                       offered=self._json(offered), requested=self._json(requested))
        with self._atomic(db):
            cycle, phase, now = self._context(db, cycle_id, now)
            self.economy._actor(db, clan_id, actor_id, trader=True)
            prior = self._receipt(db, cycle.season_id, command_id, payload)
            if prior is not None:
                return db.get(CycleMarketOffer, prior['offer_id'])
            self._land(db, clan_id)
            if target_clan_id is not None:
                if target_clan_id == clan_id or self._hostile(db, cycle, clan_id, target_clan_id, now):
                    raise ValueError('Distinct nonhostile target required')
                self._land(db, target_clan_id)
                self._route(db, clan_id, target_clan_id)
            wallet = self._wallets(db, cycle.season_id, clan_id)[clan_id]
            self._revision(wallet, expected_wallet_revision)
            remaining = rules.debit(self.economy.balance(wallet), offered)
            first = first_full_cycle(cycle.number, phase)
            offer = CycleMarketOffer(season_id=cycle.season_id, sender_clan_id=clan_id,
                target_clan_id=target_clan_id, offered=self._json(offered), requested=self._json(requested),
                created_at=now, first_full_cycle=first, expires_after_cycle=first + 1)
            self.economy._write(db, wallet, wallet=self.economy._wallet(remaining))
            db.add(offer)
            db.flush()
            self._receipt(db, cycle.season_id, command_id, payload, {'offer_id': offer.id})
            return offer

    @staticmethod
    def _offer(db, cycle, offer_id):
        row = db.query(CycleMarketOffer).filter_by(id=offer_id, season_id=cycle.season_id
            ).with_for_update().populate_existing().one_or_none()
        if row is None:
            raise ValueError('Unknown seasonal offer')
        return row

    def accept(self, db, *, cycle_id, offer_id, clan_id, actor_id, now, command_id,
               expected_revision, expected_sender_revision, expected_wallet_revision):
        payload = dict(kind='accept', offer=offer_id, clan=clan_id, actor=actor_id)
        with self._atomic(db):
            cycle, _, now = self._context(db, cycle_id, now)
            prior = self._receipt(db, cycle.season_id, command_id, payload)
            offer = self._offer(db, cycle, offer_id)
            self.economy._actor(db, clan_id, actor_id, trader=True)
            if prior is not None:
                return offer
            self._revision(offer, expected_revision)
            if offer.status != 'pending' or _cursor(cycle, now) > offer.expires_after_cycle:
                raise ValueError('Offer is not pending or has expired')
            if now < as_utc(offer.created_at):
                raise ValueError('Offer not yet created')
            sender = offer.sender_clan_id
            if clan_id == sender or offer.target_clan_id not in (None, clan_id):
                raise PermissionError('Only an eligible recipient can accept')
            if self._hostile(db, cycle, sender, clan_id, now):
                raise ValueError('Hostile clans cannot trade')
            self._land(db, sender)
            self._land(db, clan_id)
            route = self._route(db, sender, clan_id)
            timing = CampaignRuleService().get_active(db, create=False)
            hours = ClanMarketService.travel_hours(route, timing.values)
            wallets = self._wallets(db, cycle.season_id, sender, clan_id)
            first, second = wallets[sender], wallets[clan_id]
            self._revision(first, expected_sender_revision)
            self._revision(second, expected_wallet_revision)
            offered, requested = self._cargo(offer.offered), self._cargo(offer.requested)
            quote = rules.accept_barter(self.economy.balance(first) + offered,
                                        self.economy.balance(second), offered, requested)
            snapshot = dict(territory_ids=[t.id for t in route.territories], modes=list(route.modes),
                            travel_steps=route.travel_steps, travel_hours=hours, rule_version=timing.version)
            self.economy._write(db, first, wallet=self.economy._wallet(quote.first_balance))
            self.economy._write(db, second, wallet=self.economy._wallet(quote.second_balance))
            for recipient, cargo, reverse in ((sender, requested, True), (clan_id, offered, False)):
                saved = {**snapshot, 'territory_ids': list(reversed(snapshot['territory_ids'])) if reverse else snapshot['territory_ids'],
                         'modes': list(reversed(snapshot['modes'])) if reverse else snapshot['modes']}
                db.add(CycleMarketCaravan(offer_id=offer.id, recipient_clan_id=recipient,
                    cargo=self._json(cargo), route=saved, departed_at=now, arrives_at=now + timedelta(hours=hours)))
            offer.status, offer.accepter_clan_id, offer.accepted_at = 'accepted', clan_id, now
            offer.revision += 1
            self._receipt(db, cycle.season_id, command_id, payload, {'offer_id': offer.id})
            return offer

    def quote(self, db, *, cycle_id, offer_id, clan_id, actor_id, now):
        cycle, _, now = self._context(db, cycle_id, now)
        offer = self._offer(db, cycle, offer_id)
        self.economy._actor(db, clan_id, actor_id, trader=True)
        if offer.sender_clan_id == clan_id or offer.target_clan_id not in (None, clan_id):
            raise PermissionError('Only an eligible recipient can quote acceptance')
        if offer.status != 'pending' or _cursor(cycle, now) > offer.expires_after_cycle or now < as_utc(offer.created_at):
            raise ValueError('Offer is no longer pending')
        sender = offer.sender_clan_id
        if self._hostile(db, cycle, sender, clan_id, now):
            raise ValueError('Hostile clans cannot trade')
        self._land(db, sender)
        self._land(db, clan_id)
        route = self._route(db, sender, clan_id)
        wallets = self._wallets(db, cycle.season_id, sender, clan_id)
        first, second = wallets[sender], wallets[clan_id]
        quote = rules.accept_barter(self.economy.balance(first) + self._cargo(offer.offered),
                                   self.economy.balance(second), self._cargo(offer.offered), self._cargo(offer.requested))
        timing = CampaignRuleService().get_active(db, create=False)
        hours = ClanMarketService.travel_hours(route, timing.values)
        return dict(expected_revision=offer.revision, expected_sender_revision=first.revision,
                    expected_wallet_revision=second.revision, fee_gold=str(quote.second_fee),
                    travel_hours=hours, arrives_at=now + timedelta(hours=hours))

    def _refund(self, db, offer, status):
        wallet = self._wallets(db, offer.season_id, offer.sender_clan_id)[offer.sender_clan_id]
        self.economy._write(db, wallet, wallet=self.economy._wallet(
            self.economy.balance(wallet) + self._cargo(offer.offered)))
        offer.status = status
        offer.revision += 1

    def cancel(self, db, *, cycle_id, offer_id, clan_id, actor_id, now, command_id,
               expected_revision, expected_wallet_revision):
        payload = dict(kind='cancel', offer=offer_id, clan=clan_id, actor=actor_id)
        with self._atomic(db):
            cycle, _, now = self._context(db, cycle_id, now)
            prior = self._receipt(db, cycle.season_id, command_id, payload)
            offer = self._offer(db, cycle, offer_id)
            self.economy._actor(db, clan_id, actor_id, trader=True)
            if offer.sender_clan_id != clan_id:
                raise PermissionError('Only sender cancels')
            if prior is not None:
                return offer
            self._revision(offer, expected_revision)
            if offer.status != 'pending':
                raise ValueError('Only pending offers can be cancelled')
            wallet = self._wallets(db, cycle.season_id, clan_id)[clan_id]
            self._revision(wallet, expected_wallet_revision)
            self._refund(db, offer, 'cancelled')
            self._receipt(db, cycle.season_id, command_id, payload, {'offer_id': offer.id})
            return offer

    def _close_pending(self, db, *, cycle_id, now, command_id, pair=None):
        payload = dict(kind='war' if pair else 'expire', pair=sorted(pair) if pair else None, cycle=cycle_id)
        with self._atomic(db):
            cycle, _, now = self._context(db, cycle_id, now, manual=False)
            prior = self._receipt(db, cycle.season_id, command_id, payload)
            if prior is not None:
                return prior['offer_ids']
            if pair and not self._hostile(db, cycle, *pair, now):
                raise ValueError('Pair must be hostile')
            rows = db.query(CycleMarketOffer).filter_by(season_id=cycle.season_id, status='pending'
                ).order_by(CycleMarketOffer.id).with_for_update().populate_existing().all()
            closed = []
            for offer in rows:
                matches = (offer.target_clan_id is not None and
                           sorted((offer.sender_clan_id, offer.target_clan_id)) == sorted(pair)) if pair else (
                           _cursor(cycle, now) > offer.expires_after_cycle)
                if matches:
                    self._refund(db, offer, 'war_cancelled' if pair else 'expired')
                    closed.append(offer.id)
            self._receipt(db, cycle.season_id, command_id, payload, {'offer_ids': closed})
            return closed

    def expire(self, db, **kwargs):
        return self._close_pending(db, **kwargs)

    def cancel_hostile_pair(self, db, *, clan_id, other_clan_id, **kwargs):
        return self._close_pending(db, pair=(clan_id, other_clan_id), **kwargs)

    def deliver(self, db, *, cycle_id, caravan_id, now, command_id, expected_revision,
                expected_wallet_revision):
        payload = dict(kind='deliver', caravan=caravan_id)
        with self._atomic(db):
            cycle, _, now = self._context(db, cycle_id, now, manual=False)
            prior = self._receipt(db, cycle.season_id, command_id, payload)
            offer_id = db.query(CycleMarketCaravan.offer_id).filter_by(id=caravan_id).scalar()
            offer = self._offer(db, cycle, offer_id)
            caravan = db.query(CycleMarketCaravan).filter_by(id=caravan_id).with_for_update().populate_existing().one()
            if prior is not None:
                return caravan
            if caravan.delivered_at is not None:
                self._receipt(db, cycle.season_id, command_id, payload, {'caravan_id': caravan.id})
                return caravan
            self._revision(caravan, expected_revision)
            if offer.status != 'accepted' or now < as_utc(caravan.arrives_at):
                raise ValueError('Accepted caravan is not due')
            wallet = self._wallets(db, cycle.season_id, caravan.recipient_clan_id)[caravan.recipient_clan_id]
            self._revision(wallet, expected_wallet_revision)
            self.economy._write(db, wallet, wallet=self.economy._wallet(
                self.economy.balance(wallet) + self._cargo(caravan.cargo)))
            caravan.delivered_at = now
            caravan.revision += 1
            self._receipt(db, cycle.season_id, command_id, payload, {'caravan_id': caravan.id})
            return caravan
