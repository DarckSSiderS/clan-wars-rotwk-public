"""Caller-owned startup transactions. No reset of personal data or development.

Trusted parent calls initialize at season start, qualify after membership/identity
changes, and expire at the 72h boundary before ordinary attacks. qualify scans all
current verified memberships, not the requesting clan. Call it at each membership
change: departed members and historical verification cannot be reconstructed from
current rows. Durable slots/UUIDs are never recycled. The selected four must still
be current verified members at claim; dropping them does not release the receipt.

Locks: first cycle -> season -> startup -> clans/members -> territories sorted.
SQLite tests cover stale attempts, not PostgreSQL concurrent row-lock execution.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.clan import Clan, ClanMember
from app.models.external_identity import ExternalPlayerIdentity
from app.models.cycle_startup import CycleStartup, CycleStartupClan, CycleStartupIdentity
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.services.campaign_cycle_service import _utc
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_starting_lands import validate_starting_triple, qualifies_for_starting_slot, selection_world


SOURCE = 'bfmeladder'


class CycleStartupService:
    @staticmethod
    @contextmanager
    def _atomic(db):
        with CycleEconomyStore._atomic(db):
            yield

    @staticmethod
    def _context(db, cycle_id, now):
        now = _utc(now)
        cycle = CampaignCycleStore()._locked(db, cycle_id)
        season = db.query(CampaignSeason).filter_by(id=cycle.season_id).with_for_update().populate_existing().one()
        if (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
            raise ValueError('Season must explicitly enable cycle_v1')
        if season.status != 'active' or cycle.number != 1:
            raise ValueError('Active season first cycle required')
        if now < as_utc(season.starts_at):
            raise ValueError('Season has not started')
        if db.query(CampaignCycleRecord.id).filter(CampaignCycleRecord.season_id == season.id,
                                                   CampaignCycleRecord.number > 1).first():
            raise ValueError('Startup first cycle is no longer current')
        if as_utc(cycle.starts_at) != as_utc(season.starts_at) or as_utc(cycle.preparation_at) != as_utc(season.starts_at) + timedelta(hours=72):
            raise ValueError('First preparation must follow the 72h startup')
        return cycle, season, now

    @staticmethod
    def _startup(db, season_id):
        row = db.query(CycleStartup).filter_by(season_id=season_id).with_for_update().populate_existing().one_or_none()
        if row is None:
            raise ValueError('Trusted startup initialization required before claims')
        return row

    @staticmethod
    def _open(startup, now):
        if startup.expired_at is not None or now >= as_utc(startup.deadline):
            raise ValueError('Startup deadline reached; use normal attacks, no automatic gift')

    @staticmethod
    def _rows(db, season_id):
        return {r.clan_id: r for r in db.query(CycleStartupClan).filter_by(season_id=season_id)
                .order_by(CycleStartupClan.clan_id).with_for_update().populate_existing().all()}

    def initialize(self, db, *, cycle_id, now):
        """Trusted explicit season-start operation, not a public lazy initializer.

        Retry returns the original snapshot, never recaptures changed ownership.
        No ownership is transferred and no accounts/economy/upgrades are reset.
        """
        with self._atomic(db):
            cycle, season, now = self._context(db, cycle_id, now)
            existing = db.query(CycleStartup).filter_by(season_id=season.id).one_or_none()
            if existing is not None:
                return existing
            if now != as_utc(season.starts_at):
                raise ValueError('Initial ownership must be captured at explicit season start')
            lands = db.query(Territory).order_by(Territory.id).with_for_update().populate_existing().all()
            startup = CycleStartup(season_id=season.id, cycle_id=cycle.id, starts_at=now,
                deadline=now + timedelta(hours=72), initialized_at=now,
                initial_owners={str(t.id): t.owner_clan_id for t in lands})
            db.add(startup)
            db.flush()
            owned = {}
            for land in lands:
                if land.owner_clan_id is not None:
                    owned.setdefault(land.owner_clan_id, []).append(land.id)
            for clan_id, ids in sorted(owned.items()):
                db.add(CycleStartupClan(season_id=season.id, clan_id=clan_id, initial_owned=ids))
            db.flush()
            return startup

    @staticmethod
    def _members(db, now):
        clans = db.query(Clan).filter(Clan.is_deleted.is_(False)).order_by(Clan.id).with_for_update().populate_existing().all()
        members = db.query(ClanMember).order_by(ClanMember.clan_id, ClanMember.user_id
            ).with_for_update().populate_existing().all()
        identities = db.query(ExternalPlayerIdentity).filter_by(source=SOURCE, verification_status='verified'
            ).order_by(ExternalPlayerIdentity.id).with_for_update().populate_existing().all()
        verified = {}
        for identity in identities:
            try:
                uuid = str(UUID(identity.external_uuid))
            except (ValueError, TypeError, AttributeError):
                continue
            if identity.verified_at is not None and as_utc(identity.verified_at) > now:
                continue
            verified[identity.user_id] = uuid
        eligible = {c.id: [] for c in clans}
        for member in members:
            if member.clan_id not in eligible or member.user_id not in verified or member.joined_at is None:
                continue
            joined = as_utc(member.joined_at)
            if joined <= now:
                eligible[member.clan_id].append(dict(user_id=member.user_id, source=SOURCE,
                    uuid=verified[member.user_id], joined_at=joined.isoformat()))
        for clan_id in eligible:
            eligible[clan_id].sort(key=lambda m: (m['joined_at'], m['user_id']))
        return eligible

    def _projection(self, db, startup, now):
        rows = self._rows(db, startup.season_id)
        members = self._members(db, now)
        used = {r.external_uuid for r in db.query(CycleStartupIdentity).filter_by(season_id=startup.season_id).all()}
        count = sum(r.slot is not None for r in rows.values())
        season = db.get(CampaignSeason, startup.season_id)
        preparation_id = (season.rules_snapshot or {}).get('preseason_preparation_id')
        if preparation_id:
            from app.models.preseason import CampaignPreseason
            parent = db.get(CampaignPreseason, preparation_id)
            receipts = list((parent.qualifications or {}).values())
            used.update(m['uuid'] for receipt in receipts for m in receipt['selected_four'])
            count = max(count, max((r['slot'] for r in receipts), default=0))
        candidates = []
        for clan_id, available in members.items():
            row = rows.get(clan_id)
            if row and (row.initial_owned or row.slot is not None or row.status != 'pending'):
                continue
            # Only the selected four consume identities, not the rest of a roster.
            four, seen = [], set(used)
            for member in available:
                if member['uuid'] not in seen:
                    four.append(member)
                    seen.add(member['uuid'])
                if len(four) == 4:
                    break
            if qualifies_for_starting_slot([m['uuid'] for m in four], already_used=used):
                candidates.append((datetime.fromisoformat(four[-1]['joined_at']), clan_id, four))
        planned = []
        for attained, clan_id, four in sorted(candidates, key=lambda c: (c[0], c[1])):
            if count >= 6:
                break
            if not qualifies_for_starting_slot([m['uuid'] for m in four], already_used=used):
                continue
            count += 1
            planned.append(dict(clan_id=clan_id, slot=count, qualified_at=attained, selected_four=four))
            used.update(m['uuid'] for m in four)
        return rows, members, planned

    def _qualify(self, db, startup, now):
        rows, members, planned = self._projection(db, startup, now)
        for plan in planned:
            clan_id = plan['clan_id']
            row = rows.get(clan_id)
            if row is None:
                row = CycleStartupClan(season_id=startup.season_id, clan_id=clan_id, initial_owned=[])
                db.add(row)
                rows[clan_id] = row
            row.slot = plan['slot']
            row.qualified_at = plan['qualified_at']
            row.selected_four = plan['selected_four']
            for member in row.selected_four:
                db.add(CycleStartupIdentity(season_id=startup.season_id, clan_id=clan_id,
                                            source=SOURCE, external_uuid=member['uuid']))
        db.flush()
        return rows, members

    def qualify(self, db, *, cycle_id, now):
        """Trusted all-clan membership-change hook, not browser request ordering."""
        with self._atomic(db):
            _, season, now = self._context(db, cycle_id, now)
            startup = self._startup(db, season.id)
            self._open(startup, now)
            rows, _ = self._qualify(db, startup, now)
            return sorted((r for r in rows.values() if r.slot is not None), key=lambda r: r.slot)

    @staticmethod
    def _world(lands):
        return [SimpleNamespace(id=t.id, owner_clan_id=t.owner_clan_id,
            neighbours=tuple(t.adjacent_territory_ids or ()), port=t.has_port,
            fortress=t.is_great_stronghold) for t in lands if t.is_playable]

    def selection_world(self, db, season, startup, lands, rows):
        world = self._world(lands)
        if (season.rules_snapshot or {}).get('preseason_preparation_id'):
            resolved = {r.clan_id for r in rows.values() if r.status != 'pending'}
            active = {c.id for c in db.query(Clan).filter_by(is_deleted=False, is_admin_clan=False)}
            resolved.update(owner for owner in startup.initial_owners.values() if owner not in active)
            world = selection_world(world, startup.initial_owners, resolved)
        return world

    @staticmethod
    def _authorize(db, clan_id, actor_id):
        CycleEconomyStore._actor(db, clan_id, actor_id)

    @staticmethod
    def _current_four(row, members):
        current = {(m['user_id'], m['source'], m['uuid']) for m in members.get(row.clan_id, [])}
        if len(row.selected_four) != 4 or any((m['user_id'], m['source'], m['uuid']) not in current for m in row.selected_four):
            raise ValueError('Selected four must remain current verified members; qualification is not recycled')

    def preview(self, db, *, cycle_id, clan_id, actor_id, selected, now):
        """Read-only projection: no receipts, reservation, transfers or auto-choice."""
        _, season, now = self._context(db, cycle_id, now)
        startup = self._startup(db, season.id)
        self._open(startup, now)
        self._authorize(db, clan_id, actor_id)
        rows, members, planned = self._projection(db, startup, now)
        row = rows.get(clan_id)
        plan = next((p for p in planned if p['clan_id'] == clan_id), None)
        if row is None and plan is None:
            raise ValueError('Clan is not eligible for starting lands')
        initial = row.initial_owned if row else []
        if row and row.status != 'pending':
            raise ValueError('Startup choice already resolved')
        if not initial:
            if not (row and row.slot is not None) and plan is None:
                raise ValueError('Clan is not eligible for starting lands')
            if row and row.slot is not None:
                self._current_four(row, members)
        lands = db.query(Territory).order_by(Territory.id).populate_existing().all()
        chosen = validate_starting_triple(selected, clan_id=clan_id, initial_owned=initial,
                                          territories=self.selection_world(db, season, startup, lands, rows))
        return dict(selected=list(chosen), release=[t.id for t in lands if t.id in initial
                    and t.id not in chosen and t.owner_clan_id == clan_id],
                    basis='retention' if initial else 'gift', slot=row.slot if row else plan['slot'])

    @staticmethod
    def _transfer(db, territory, owner, now, reason, startup):
        """Local trusted transfer: history only, no legacy influence/economy reset."""
        previous = territory.owner_clan_id
        if previous == owner:
            if owner is not None and not db.query(TerritoryOwnershipHistory).filter_by(
                    territory_id=territory.id, clan_id=owner, ended_at=None).first():
                db.add(TerritoryOwnershipHistory(territory_id=territory.id, clan_id=owner,
                                                started_at=now, reason=reason))
            return
        histories = db.query(TerritoryOwnershipHistory).filter_by(territory_id=territory.id,
            ended_at=None).with_for_update().all()
        for history in histories:
            history.ended_at = now
        if previous is not None and not histories:
            db.add(TerritoryOwnershipHistory(territory_id=territory.id, clan_id=previous,
                started_at=territory.owned_since or startup.starts_at, ended_at=now, reason=reason))
        territory.owner_clan_id = owner
        territory.owned_since = now if owner is not None else None
        territory.last_weekly_payout_at = None
        territory.resource_income_ready_at = None
        territory.last_resource_payout_at = None
        if owner is not None:
            db.add(TerritoryOwnershipHistory(territory_id=territory.id, clan_id=owner,
                                             started_at=now, reason=reason))

    def claim(self, db, *, cycle_id, clan_id, actor_id, selected, now, expected_revision=1):
        selected = tuple(selected)
        if len(selected) != 3 or any(type(i) is not int for i in selected) or len(set(selected)) != 3:
            raise ValueError('Three distinct integer territory IDs required')
        with self._atomic(db):
            cycle, season, now = self._context(db, cycle_id, now)
            startup = self._startup(db, season.id)
            self._authorize(db, clan_id, actor_id)
            row = self._rows(db, season.id).get(clan_id)
            if row and row.status == 'claimed':
                if sorted(selected) != row.selected_lands:
                    raise CycleConflict('Starting claim is immutable')
                return row
            self._open(startup, now)
            rows, members = self._qualify(db, startup, now)
            row = rows.get(clan_id)
            if row is None or (not row.initial_owned and row.slot is None):
                raise ValueError('Clan is not eligible for starting lands')
            if type(expected_revision) is not int or row.revision != expected_revision:
                raise CycleConflict('Startup revision changed')
            if row.status != 'pending':
                raise ValueError('Startup choice already resolved')
            if not row.initial_owned:
                self._current_four(row, members)
            # Lock the validation world too: availability/retention feasibility
            # must not change between validation and the ownership updates.
            lands = db.query(Territory).order_by(Territory.id).with_for_update().populate_existing().all()
            chosen = validate_starting_triple(selected, clan_id=clan_id, initial_owned=row.initial_owned,
                                              territories=self.selection_world(db, season, startup, lands, rows))
            for land in lands:
                if land.id in chosen:
                    self._transfer(db, land, clan_id, now, 'cycle_startup_claim', startup)
                elif land.id in row.initial_owned and land.owner_clan_id == clan_id:
                    self._transfer(db, land, None, now, 'cycle_startup_release', startup)
            row.selected_lands, row.claimed_at, row.status = list(chosen), now, 'claimed'
            row.revision += 1
            db.flush()
            self._refresh_launch_influence(db, season, cycle, [clan_id], now)
            return row

    @staticmethod
    def _refresh_launch_influence(db, season, cycle, clan_ids, now):
        if not (season.rules_snapshot or {}).get('launch_command_id'):
            return
        from app.models.campaign import CampaignRuleSet
        from app.services.cycle_ownership_service import CycleOwnershipService
        rule = db.get(CampaignRuleSet, season.rules_snapshot['rule_set_id'])
        if rule is None:
            raise ValueError('Не найдены зафиксированные правила нового сезона')
        for clan_id in sorted(clan_ids):
            CycleOwnershipService._recalculate(db, clan_id, cycle, rule, now)

    def expire(self, db, *, cycle_id, now):
        """Trusted deadline hook; no auto-selection or slot/UUID recycling."""
        with self._atomic(db):
            cycle, season, now = self._context(db, cycle_id, now)
            startup = self._startup(db, season.id)
            if now < as_utc(startup.deadline):
                raise ValueError('Startup deadline has not arrived')
            if startup.expired_at is not None:
                return startup
            rows = self._rows(db, season.id)
            lands = db.query(Territory).order_by(Territory.id).with_for_update().populate_existing().all()
            for row in rows.values():
                if row.status != 'pending':
                    continue
                for land in lands:
                    if land.id in row.initial_owned and land.owner_clan_id == row.clan_id:
                        self._transfer(db, land, None, as_utc(startup.deadline), 'cycle_startup_expiry', startup)
                row.status = 'expired'
                row.revision += 1
            startup.expired_at = now
            db.flush()
            self._refresh_launch_influence(db, season, cycle, rows, now)
            return startup
