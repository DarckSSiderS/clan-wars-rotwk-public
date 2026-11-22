"""Caller-owned transactions for cycle_v1 only. No commits or implicit income.

Keep state rows for the season lifetime: their existence is the starter grant
receipt. Do not delete/recreate them during clan soft deletion. System callers
own reveal scheduling; freeze_snapshot never changes an existing snapshot.
The caller must freeze at reveal before permitting post-reveal mutations:
a delayed first capture cannot reconstruct historical relics or land ownership.
"""

from contextlib import contextmanager
from decimal import Decimal

from sqlalchemy import select, update

from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.clan import Clan, ClanMember
from app.models.territory import Territory
from app.models.cycle_economy import CycleEconomyState, CycleEconomySnapshot, CycleTerritoryUpgrade
from app.services import cycle_economy as rules
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.campaign_cycle_service import _utc


class EconomyConflict(ValueError):
    """Refresh revisions before retrying; caller may roll back its transaction."""


class CycleEconomyStore:
    @staticmethod
    @contextmanager
    def _atomic(db):
        # sqlite3 legacy mode does not BEGIN on SELECT: otherwise releasing the
        # first SAVEPOINT commits work that the caller expects to roll back.
        connection = db.connection()
        if connection.dialect.name == 'sqlite' and not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql('BEGIN')
        try:
            with db.begin_nested():
                yield
        except Exception:
            # Bulk CAS writes followed by refresh are not marked ORM-dirty;
            # savepoint rollback alone can leave their cached values stale.
            db.expire_all()
            raise

    @staticmethod
    def balance(state):
        return rules.Resources(**state.wallet)

    @staticmethod
    def _wallet(balance):
        return {key: str(getattr(balance, key)) for key in rules.RESOURCE_NAMES}

    @staticmethod
    def _season(db, season_id):
        row = db.execute(select(CampaignSeason).where(CampaignSeason.id == season_id)
                         .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
        if row is None or (row.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
            raise ValueError('Season must explicitly enable cycle_v1')
        if row.status != 'active':
            raise ValueError('An active season is required')
        return row

    @staticmethod
    def _actor(db, clan_id, actor_id, *, trader=False):
        clan = db.execute(select(Clan).where(Clan.id == clan_id).with_for_update()
                          .execution_options(populate_existing=True)).scalar_one_or_none()
        if clan is None or clan.is_deleted:
            raise PermissionError('An existing active clan is required')
        if type(actor_id) is not int:
            raise PermissionError('Database user ID required')
        if clan.leader_id == actor_id:
            return
        if trader and db.execute(select(ClanMember.id).where(
                ClanMember.clan_id == clan_id, ClanMember.user_id == actor_id,
                ClanMember.is_trader.is_(True)).with_for_update()).first():
            return
        raise PermissionError('Clan head' + (' or appointed trader' if trader else '') + ' required')

    def ensure_state(self, db, *, season_id, clan_id):
        self._season(db, season_id)
        clan = db.execute(select(Clan.id).where(Clan.id == clan_id, Clan.is_deleted.is_(False))
                          .with_for_update()).first()
        if clan is None:
            raise ValueError('Unknown active clan')
        row = db.execute(select(CycleEconomyState).where(
            CycleEconomyState.season_id == season_id, CycleEconomyState.clan_id == clan_id)
            .execution_options(populate_existing=True)).scalar_one_or_none()
        if row is None:
            row = CycleEconomyState(season_id=season_id, clan_id=clan_id,
                                    wallet=self._wallet(rules.START_RESOURCES))
            db.add(row)
            db.flush()
        return row

    start = ensure_state

    def _state(self, db, state_id, expected_revision):
        if type(expected_revision) is not int or expected_revision < 1:
            raise EconomyConflict('A positive expected revision is required')
        # Read only the season key first; acquire locks in season -> state order.
        season_id = db.execute(select(CycleEconomyState.season_id).where(
            CycleEconomyState.id == state_id)).scalar_one_or_none()
        if season_id is None:
            raise ValueError('Unknown economy state')
        self._season(db, season_id)
        row = db.execute(select(CycleEconomyState).where(CycleEconomyState.id == state_id)
                         .with_for_update().execution_options(populate_existing=True)).scalar_one()
        if row.revision != expected_revision:
            raise EconomyConflict('Economy revision changed')
        return row

    @staticmethod
    def _write(db, row, **values):
        result = db.execute(update(CycleEconomyState).where(
            CycleEconomyState.id == row.id, CycleEconomyState.revision == row.revision)
            .values(**values, revision=row.revision + 1).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise EconomyConflict('Concurrent economy update')
        db.refresh(row)
        return row

    def choose_starters(self, db, *, state_id, actor_id, selected, expected_revision):
        """Available once even for late clans; registration does not activate them."""
        row = self._state(db, state_id, expected_revision)
        self._actor(db, row.clan_id, actor_id)
        if row.starters_chosen:
            raise ValueError('Starter relics already chosen')
        gifts = rules.starting_relics(selected)
        if set(gifts) & set(row.relics):
            raise ValueError('Choose two unowned starter relics')
        return self._write(db, row, relics={**row.relics, **gifts}, starters_chosen=True)

    def buy_relic(self, db, *, state_id, actor_id, key, expected_revision):
        row = self._state(db, state_id, expected_revision)
        self._actor(db, row.clan_id, actor_id)
        balance, relics = rules.buy_relic(self.balance(row), row.relics, key)
        return self._write(db, row, wallet=self._wallet(balance), relics=relics)

    @staticmethod
    def _cycle(db, state_id, cycle_id):
        # Match the plan freezer: cycle -> season -> wallet. Never wait for a
        # cycle lock while holding the wallet/season locks it needs to freeze.
        season_id = db.execute(select(CycleEconomyState.season_id).where(
            CycleEconomyState.id == state_id)).scalar_one_or_none()
        cycle = db.execute(select(CampaignCycleRecord).where(CampaignCycleRecord.id == cycle_id)
                           .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
        if cycle is None or cycle.season_id != season_id:
            raise ValueError('Cycle must belong to the economy season')
        latest = db.execute(select(CampaignCycleRecord.id).where(
            CampaignCycleRecord.season_id == season_id,
            CampaignCycleRecord.number > cycle.number)).first()
        if latest:
            raise ValueError('Only the latest cycle can be used')
        return cycle

    def select_active(self, db, *, state_id, actor_id, cycle_id, now, selected, expected_revision):
        cycle = self._cycle(db, state_id, cycle_id)
        row = self._state(db, state_id, expected_revision)
        self._actor(db, row.clan_id, actor_id)
        phase = CampaignCycleStore.timeline(cycle).phase_at(now).value
        active = rules.select_relics(row.relics, selected, phase=phase)
        return self._write(db, row, active_relics=list(active))

    def freeze_snapshot(self, db, *, state_id, cycle_id, now, expected_revision):
        """Trusted system entry point at/after reveal (battle_at), never user auth."""
        with self._atomic(db):
            cycle = self._cycle(db, state_id, cycle_id)
            row = self._state(db, state_id, expected_revision)
            now = _utc(now)
            if now < CampaignCycleStore.timeline(cycle).battle_at:
                raise ValueError('Reveal has not started')
            existing = db.execute(select(CycleEconomySnapshot).where(
                CycleEconomySnapshot.state_id == row.id,
                CycleEconomySnapshot.cycle_id == cycle.id)).scalar_one_or_none()
            if existing is not None:
                return existing
            effects = [dict(key=e.key, level=e.level, effect=e.effect, percent=str(e.percent))
                       for e in rules.relic_snapshot(row.relics, row.active_relics)]
            lands = db.execute(select(CycleTerritoryUpgrade).join(Territory,
                Territory.id == CycleTerritoryUpgrade.territory_id).where(
                    CycleTerritoryUpgrade.season_id == row.season_id,
                    Territory.owner_clan_id == row.clan_id)).scalars().all()
            snapshot = CycleEconomySnapshot(cycle_id=cycle.id, state_id=row.id,
                effects=effects, territory_upgrades={str(land.territory_id): dict(land.levels) for land in lands},
                frozen_at=now, state_revision=row.revision)
            self._write(db, row)
            db.add(snapshot)
            db.flush()
            return snapshot

    def buy_upgrade(self, db, *, state_id, actor_id, territory_id, branch, expected_revision,
                    expected_upgrade_revision):
        """Absent land state has revision 0; land CAS supplements wallet CAS."""
        with self._atomic(db):
            row = self._state(db, state_id, expected_revision)
            self._actor(db, row.clan_id, actor_id)
            land = db.execute(select(Territory).where(Territory.id == territory_id)
                              .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
            if land is None or land.owner_clan_id != row.clan_id:
                raise PermissionError('Territory ownership required')
            if branch == 'profile' and (land.resource_type not in ('iron', 'wood', 'food')
                                         or (land.resource_output or 0) <= 0):
                raise ValueError('A producing iron, wood or food profile is required')
            if branch == 'mithril' and (land.resource_type != 'mithril'
                                         or (land.resource_output or 0) <= 0):
                raise ValueError('A producing mithril profile is required')
            if branch == 'naval' and not land.has_port:
                raise ValueError('A port is required for naval upgrades')
            upgrade = db.get(CycleTerritoryUpgrade, (row.season_id, territory_id), populate_existing=True)
            revision = upgrade.revision if upgrade else 0
            if type(expected_upgrade_revision) is not int or expected_upgrade_revision != revision:
                raise EconomyConflict('Territory upgrade revision changed')
            levels = dict(upgrade.levels) if upgrade else {}
            snapshot = self.upgrade_effects(db, row)
            cost = rules.upgrade_cost(branch, levels.get(branch, 0), snapshot)
            remaining = rules.debit(self.balance(row), cost)
            self._write(db, row, wallet=self._wallet(remaining))
            levels[branch] = levels.get(branch, 0) + 1
            if upgrade:
                upgrade.levels = levels
                upgrade.revision += 1
            else:
                db.add(CycleTerritoryUpgrade(season_id=row.season_id, territory_id=territory_id, levels=levels))
            db.flush()
            return row

    @staticmethod
    def upgrade_effects(db, row):
        latest_cycle = db.execute(select(CampaignCycleRecord).where(
            CampaignCycleRecord.season_id == row.season_id).order_by(
                CampaignCycleRecord.number.desc()).limit(1)).scalar_one_or_none()
        frozen = None if latest_cycle is None or latest_cycle.settled_at is not None else db.execute(select(CycleEconomySnapshot).where(
            CycleEconomySnapshot.state_id == row.id,
            CycleEconomySnapshot.cycle_id == latest_cycle.id)).scalar_one_or_none()
        return (tuple(rules.RelicEffect(e['key'], e['level'], e['effect'], Decimal(e['percent']))
                      for e in frozen.effects) if frozen else rules.relic_snapshot(row.relics, row.active_relics))

    def market(self, db, *, state_id, actor_id, resource, quantity, buying, expected_revision):
        row = self._state(db, state_id, expected_revision)
        self._actor(db, row.clan_id, actor_id, trader=True)
        remaining = rules.system_market(self.balance(row), resource, quantity, buying=buying)
        return self._write(db, row, wallet=self._wallet(remaining))
