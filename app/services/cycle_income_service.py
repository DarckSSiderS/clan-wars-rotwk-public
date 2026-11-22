"""Independent, trusted-system income entry points; caller supplies UTC time.

No commits, scheduler, legacy balances, population or resource-wealth inference.
Register the models and migrate their tables in the parent application. Admin
authorization for configure_profile belongs to that trusted caller, not a flag
accepted from an HTTP request. Profiles are explicit balance decisions, never
generated from category/port/fortress flags (ECONOMY_BALANCE_2026-10-11.md).

INTEGRATION CONTRACT: accrue ALL affected states before upgrade, relic-level,
loadout or ownership mutations, at reveal before freezing, and at settlement
before unfreezing. Do so in the SAME caller transaction, using the same now.
Persist complete, nonoverlapping ownership history including initial grants.
History permits delayed accrual across transfers, but upgrade/loadout history
does not exist: changing them first cannot be reconstructed by this service.
Serialize cycle creation/profile configuration using the season lock. Acquire
cycle -> season -> wallet locks in that order in surrounding transactions too.
Retain receipts for the entire season; deleting one would allow double income.
Refresh ORM identities after a caller savepoint rollback: Core CAS updates are
not ORM attribute edits and SQLAlchemy may leave their cached values unchanged.

Wallet increments are decimal strings to 18 fractional places, not floats.
Exact rational sub-quantum residuals are retained separately, so frequent polls
neither lose nor manufacture fractional income. Base income is unconditional
and not relic-multiplied; territory income uses the pure economy rules.
"""

from datetime import datetime, timezone
from decimal import Decimal, localcontext
from fractions import Fraction

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.clan import Clan
from app.models.cycle_economy import CycleEconomyState, CycleEconomySnapshot, CycleTerritoryUpgrade
from app.models.cycle_income import CycleIncomeAccrual, CycleTerritoryProfile
from app.models.cycle_startup import CycleStartup, CycleStartupClan
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.services import cycle_economy as rules
from app.services.campaign_cycle_service import _utc
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_economy_store import CycleEconomyStore, EconomyConflict


def _locked(db: Session, statement):
    return db.execute(statement.with_for_update().execution_options(populate_existing=True))


def _duration(start: datetime, end: datetime) -> Fraction:
    delta = end - start
    return Fraction((delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds,
                    86400 * 1000000)


class CycleIncomeService:
    @staticmethod
    def _season(db: Session, season_id: int) -> CampaignSeason:
        season = _locked(db, select(CampaignSeason).where(CampaignSeason.id == season_id)).scalar_one_or_none()
        if season is None or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
            raise ValueError('Season must explicitly enable cycle_v1')
        return season

    @staticmethod
    def _cycles(db: Session, season_id: int) -> list[CampaignCycleRecord]:
        # The worker already holds the current cycle. Acquire older rows only
        # after that row, then return chronological order for income segments.
        rows = list(_locked(db, select(CampaignCycleRecord).where(
            CampaignCycleRecord.season_id == season_id).order_by(CampaignCycleRecord.number.desc())).scalars())
        return list(reversed(rows))

    def configure_profile(self, db: Session, *, season_id: int, territory_id: int,
                          base: rules.Resources, profile_material: str | None,
                          now: datetime) -> CycleTerritoryProfile:
        """Trusted admin input only; no exact territory mapping is supplied here.

        All changes stop at first preparation, or first income receipt if earlier.
        Rejecting changes after accrual prevents retroactive repricing of history.
        """
        now = _utc(now)
        if not isinstance(base, rules.Resources):
            raise TypeError('Canonical Resources required')
        rules.territory_income(base, profile_material)
        if profile_material is not None and not getattr(base, profile_material):
            raise ValueError('A fixed material profile requires positive base production')
        with CycleEconomyStore._atomic(db):
            cycles = self._cycles(db, season_id)
            self._season(db, season_id)
            if any(as_utc(c.preparation_at) <= now for c in cycles):
                raise ValueError('Profiles cannot change once preparation has begun')
            if db.execute(select(CycleIncomeAccrual.state_id).join(CycleEconomyState).where(
                    CycleEconomyState.season_id == season_id)).first():
                raise ValueError('Profiles cannot change after income accrual')
            territory = _locked(db, select(Territory).where(Territory.id == territory_id)).scalar_one_or_none()
            if territory is None or not territory.is_playable:
                raise ValueError('An explicitly playable territory is required')
            row = _locked(db, select(CycleTerritoryProfile).where(
                CycleTerritoryProfile.season_id == season_id,
                CycleTerritoryProfile.territory_id == territory_id)).scalar_one_or_none()
            values = dict(base=CycleEconomyStore._wallet(base), profile_material=profile_material)
            if row is None:
                row = CycleTerritoryProfile(season_id=season_id, territory_id=territory_id, **values)
                db.add(row)
                db.flush()
            else:
                result = db.execute(update(CycleTerritoryProfile).where(
                    CycleTerritoryProfile.season_id == season_id,
                    CycleTerritoryProfile.territory_id == territory_id,
                    CycleTerritoryProfile.revision == row.revision).values(
                        **values, revision=row.revision + 1).execution_options(synchronize_session=False))
                if result.rowcount != 1:
                    raise EconomyConflict('Concurrent profile update')
                db.refresh(row)
            return row

    def has_complete_profiles(self, db: Session, *, season_id: int) -> bool:
        """An empty map is not a verified configured map."""
        self._season(db, season_id)
        playable = set(db.execute(select(Territory.id).where(Territory.is_playable.is_(True))).scalars())
        profiles = list(db.execute(select(CycleTerritoryProfile).where(
            CycleTerritoryProfile.season_id == season_id)
            .execution_options(populate_existing=True)).scalars())
        for profile in profiles:
            rules.territory_income(rules.Resources(**profile.base), profile.profile_material)
        return bool(playable) and playable <= {p.territory_id for p in profiles}

    @staticmethod
    def _intervals(db: Session, clan_id: int, start: datetime, end: datetime, season_id: int):
        startup = db.get(CycleStartup, season_id, populate_existing=True)
        choice = db.execute(select(CycleStartupClan).where(
            CycleStartupClan.season_id == season_id,
            CycleStartupClan.clan_id == clan_id).execution_options(populate_existing=True)).scalar_one_or_none()
        reserved = {int(key) for key, owner in startup.initial_owners.items()
                    if owner == clan_id} if startup else set()

        def eligible_start(territory_id, held_from):
            # Old holdings reserve a starting choice; they are not new-season grants.
            if territory_id not in reserved or held_from >= as_utc(startup.deadline):
                return held_from
            if (choice is None or choice.status != 'claimed' or choice.claimed_at is None
                    or territory_id not in choice.selected_lands):
                return None
            return max(held_from, as_utc(choice.claimed_at))

        # Inspect all owners to reject overlapping histories instead of paying twice.
        histories = list(db.execute(select(TerritoryOwnershipHistory).order_by(
            TerritoryOwnershipHistory.territory_id, TerritoryOwnershipHistory.started_at,
            TerritoryOwnershipHistory.id).execution_options(populate_existing=True)).scalars())
        grouped = {}
        for row in histories:
            grouped.setdefault(row.territory_id, []).append(row)
        current = list(db.execute(select(Territory).where(Territory.owner_clan_id == clan_id)
                                  .execution_options(populate_existing=True)).scalars())
        for territory in current:
            if territory.id in reserved and eligible_start(territory.id, as_utc(startup.starts_at)) is None:
                continue
            rows = grouped.get(territory.id, [])
            if not any(r.clan_id == clan_id and r.ended_at is None for r in rows):
                raise ValueError(f'Missing current ownership history for territory {territory.id}')
        intervals = []
        for territory_id, rows in grouped.items():
            relevant = [r for r in rows if r.clan_id == clan_id and as_utc(r.started_at) < end
                        and (r.ended_at is None or as_utc(r.ended_at) > start)]
            if not relevant:
                continue
            previous_end = None
            for index, row in enumerate(rows):
                a = as_utc(row.started_at)
                b = as_utc(row.ended_at) if row.ended_at else datetime.max.replace(tzinfo=timezone.utc)
                if b <= a or (index and (previous_end is None or a < previous_end)):
                    raise ValueError(f'Overlapping or invalid ownership history for territory {territory_id}')
                previous_end = b
            for row in relevant:
                held_from = eligible_start(territory_id, as_utc(row.started_at))
                held_until = min(end, as_utc(row.ended_at)) if row.ended_at else end
                if held_from is not None and max(start, held_from) < held_until:
                    intervals.append((territory_id, max(start, held_from), held_until))
        return intervals

    @staticmethod
    def _effects(db: Session, state: CycleEconomyState, cycles: list[CampaignCycleRecord],
                 start: datetime, end: datetime):
        windows = []
        points = {start, end}
        for cycle in cycles:
            battle = CampaignCycleStore.timeline(cycle).battle_at
            finish = as_utc(cycle.settled_at) if cycle.settled_at else end
            a, b = max(start, battle), min(end, finish)
            if a < b:
                snapshot = db.execute(select(CycleEconomySnapshot).where(
                    CycleEconomySnapshot.cycle_id == cycle.id,
                    CycleEconomySnapshot.state_id == state.id)
                    .execution_options(populate_existing=True)).scalar_one_or_none()
                if snapshot is None:
                    raise ValueError(f'Missing frozen income snapshot for cycle {cycle.id}')
                effects = tuple(rules.RelicEffect(e['key'], e['level'], e['effect'], Decimal(e['percent']))
                                for e in snapshot.effects)
                windows.append((a, b, effects))
                points.update((a, b))
        live = rules.relic_snapshot(state.relics, state.active_relics)
        ordered = sorted(points)
        segments = []
        for a, b in zip(ordered, ordered[1:]):
            matches = [effects for x, y, effects in windows if x <= a < y]
            if len(matches) > 1:
                raise ValueError('Overlapping cycle income windows')
            segments.append((a, b, matches[0] if matches else live))
        return segments

    def accrue(self, db: Session, *, state_id: int, now: datetime,
               expected_revision: int | None = None) -> rules.Resources:
        """Credit [receipt, now) atomically; repeat now is a no-op.

        Future starts and backwards time are errors, not zero-credit receipts.
        Closed seasons stop at ends_at, when present; no implicit wall clock.
        Retry conflicts only after rolling back/refreshing the caller transaction.
        """
        now = _utc(now)
        with CycleEconomyStore._atomic(db):
            season_id = db.execute(select(CycleEconomyState.season_id).where(
                CycleEconomyState.id == state_id)).scalar_one_or_none()
            if season_id is None:
                raise ValueError('Unknown economy state')
            cycles = self._cycles(db, season_id)
            season = self._season(db, season_id)
            state = _locked(db, select(CycleEconomyState).where(CycleEconomyState.id == state_id)).scalar_one()
            if expected_revision is not None and state.revision != expected_revision:
                raise EconomyConflict('Economy revision changed')
            clan = db.get(Clan, state.clan_id, populate_existing=True)
            origin = max(as_utc(season.starts_at), as_utc(clan.created_at))
            if now < origin:
                raise ValueError('Accrual start is in the future')
            receipt = _locked(db, select(CycleIncomeAccrual).where(
                CycleIncomeAccrual.state_id == state_id)).scalar_one_or_none()
            start = as_utc(receipt.accrued_through) if receipt else origin
            if now < start:
                raise ValueError('Accrual time cannot move backwards')
            end = min(now, as_utc(season.ends_at)) if season.ends_at else now
            if end <= start:
                return rules.Resources()
            totals = {k: Fraction(getattr(rules.BASE_DAILY_INCOME, k)) * _duration(start, end)
                      for k in rules.RESOURCE_NAMES}
            intervals = self._intervals(db, state.clan_id, start, end, season_id)
            segments = self._effects(db, state, cycles, start, end) if intervals else []
            for territory_id, held_from, held_until in intervals:
                profile = db.get(CycleTerritoryProfile, (season_id, territory_id), populate_existing=True)
                if profile is None:
                    raise ValueError(f'Missing configured income profile for territory {territory_id}')
                upgrade = db.get(CycleTerritoryUpgrade, (season_id, territory_id), populate_existing=True)
                levels = upgrade.levels if upgrade else {}
                branch = 'mithril' if profile.profile_material == 'mithril' else 'profile'
                for a, b, effects in segments:
                    a, b = max(a, held_from), min(b, held_until)
                    if a >= b:
                        continue
                    daily = rules.territory_income(rules.Resources(**profile.base), profile.profile_material,
                        gold_level=levels.get('gold', 0), profile_level=levels.get(branch, 0), snapshot=effects)
                    for key in rules.RESOURCE_NAMES:
                        totals[key] += Fraction(getattr(daily, key)) * _duration(a, b)
            paid, residuals = {}, {}
            for key in rules.RESOURCE_NAMES:
                exact = totals[key] + Fraction((receipt.residuals if receipt else {}).get(key, '0'))
                units = exact * 10**18
                integer = units.numerator // units.denominator
                paid[key] = Decimal(f'{integer // 10**18}.{integer % 10**18:018d}')
                residuals[key] = str(exact - Fraction(integer, 10**18))
            # Addition must not round away existing large or high-scale balances.
            balance = rules.Resources(**state.wallet)
            with localcontext() as context:
                context.prec = max(60, *(len(getattr(balance, k).as_tuple().digits)
                                        + abs(getattr(balance, k).as_tuple().exponent) + 30
                                        for k in rules.RESOURCE_NAMES))
                wallet = CycleEconomyStore._wallet(balance + rules.Resources(**paid))
            CycleEconomyStore._write(db, state, wallet=wallet)
            if receipt is None:
                db.add(CycleIncomeAccrual(state_id=state_id, accrued_through=end, residuals=residuals))
                db.flush()
            else:
                changed = db.execute(update(CycleIncomeAccrual).where(
                    CycleIncomeAccrual.state_id == state_id,
                    CycleIncomeAccrual.revision == receipt.revision).values(
                        accrued_through=end, residuals=residuals, revision=receipt.revision + 1)
                    .execution_options(synchronize_session=False))
                if changed.rowcount != 1:
                    raise EconomyConflict('Concurrent income receipt update')
                db.refresh(receipt)
            return rules.Resources(**paid)
