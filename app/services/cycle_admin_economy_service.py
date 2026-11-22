"""Administrative cycle treasury corrections; the caller owns the transaction.

AdminAuditLog is also the durable command receipt. Keep these entries for the
season lifetime. The season row lock serializes receipt lookup and insertion,
including commands targeting different clans. No legacy ledger or frozen battle
snapshot is changed here.
"""

from sqlalchemy import select

from app.core import time as clock
from app.models.campaign import CampaignSeason
from app.models.clan import Clan
from app.models.cycle_economy import CycleEconomySnapshot, CycleEconomyState
from app.models.operation import AdminAuditLog
from app.models.role import Role
from app.models.user import User
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_economy import RESOURCE_NAMES, Resources
from app.services.cycle_economy_store import CycleEconomyStore, EconomyConflict
from app.services.cycle_income_service import CycleIncomeService
from app.services.operation_service import AdminAuditService


class CycleAdminEconomyService:
    action = 'cycle_clan_economy_adjusted'
    entity_type = 'cycle_economy_command'

    @staticmethod
    def _admin(db, actor_id):
        if type(actor_id) is not int or not db.execute(select(User.id).join(Role).where(
                User.id == actor_id, User.is_active.is_(True), Role.name == 'admin')).first():
            raise PermissionError('An active administrator is required')

    @staticmethod
    def _current(db):
        season = db.execute(select(CampaignSeason).where(CampaignSeason.status == 'active')
            .order_by(CampaignSeason.number.desc())
            .execution_options(populate_existing=True)).scalars().first()
        if season is None:
            season = db.execute(select(CampaignSeason).order_by(CampaignSeason.number.desc())
                .execution_options(populate_existing=True)).scalars().first()
        return season

    @staticmethod
    def _serialize(state):
        return dict(state_id=state.id, season_id=state.season_id, clan_id=state.clan_id,
                    revision=state.revision, wallet=dict(state.wallet))

    @staticmethod
    def _clan(db, clan_id):
        clan = db.execute(select(Clan).where(Clan.id == clan_id, Clan.is_deleted.is_(False))
            .execution_options(populate_existing=True)).scalar_one_or_none()
        if clan is None:
            raise ValueError('An existing active clan is required')

    @staticmethod
    def _state(db, season_id, clan_id):
        state = db.execute(select(CycleEconomyState).where(
            CycleEconomyState.season_id == season_id, CycleEconomyState.clan_id == clan_id)
            .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
        if state is None:
            raise ValueError('Seasonal economy has not been initialized')
        return state

    @staticmethod
    def _require_snapshot(db, state, cycles, now):
        latest = cycles[-1] if cycles else None
        if latest and latest.settled_at is None and now >= CampaignCycleStore.timeline(latest).battle_at:
            if db.execute(select(CycleEconomySnapshot.id).where(
                    CycleEconomySnapshot.state_id == state.id,
                    CycleEconomySnapshot.cycle_id == latest.id)).first() is None:
                raise ValueError('Reveal snapshot must be frozen before treasury corrections')

    def read(self, db, *, clan_id, actor_id):
        self._admin(db, actor_id)
        with CycleEconomyStore._atomic(db):
            self._clan(db, clan_id)
            season = self._current(db)
            mode = (season.rules_snapshot or {}).get('mechanics_version', 'legacy') if season else 'legacy'
            result = dict(mechanics_version=mode, season_id=season.id if season else None,
                          state=None)
            if mode == 'legacy':
                return result
            if mode != 'cycle_v1' or season.status != 'active':
                raise ValueError('A current active cycle_v1 season is required')
            cycles = CycleIncomeService._cycles(db, season.id)
            CycleEconomyStore._season(db, season.id)
            state = self._state(db, season.id, clan_id)
            now = clock.utc_now()
            self._require_snapshot(db, state, cycles, now)
            CycleIncomeService().accrue(db, state_id=state.id, now=now)
            result['state'] = self._serialize(state)
            return result

    def correct(self, db, *, clan_id, actor_id, season_id, wallet, reason,
                expected_revision, command_id):
        self._admin(db, actor_id)
        if not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 2000:
            raise ValueError('A reason of 3 to 2000 characters is required')
        if not isinstance(command_id, str) or not 1 <= len(command_id.strip()) <= 120:
            raise ValueError('A command ID of 1 to 120 characters is required')
        if type(expected_revision) is not int or expected_revision < 1:
            raise EconomyConflict('A positive expected revision is required')
        if not isinstance(wallet, dict) or set(wallet) != set(RESOURCE_NAMES):
            raise ValueError('A complete seasonal resource wallet is required')
        balance = Resources(**wallet)
        # Normalize equivalent decimal spellings for deterministic receipts.
        values = {}
        for key in RESOURCE_NAMES:
            value = format(getattr(balance, key), 'f')
            values[key] = (value.rstrip('0').rstrip('.') if '.' in value else value) if getattr(balance, key) else '0'
        payload = dict(season_id=season_id, clan_id=clan_id, actor_id=actor_id,
                       wallet=values, reason=reason.strip(), expected_revision=expected_revision)
        with CycleEconomyStore._atomic(db):
            cycles = CycleIncomeService._cycles(db, season_id)
            CycleEconomyStore._season(db, season_id)
            current = self._current(db)
            if current is None or current.id != season_id:
                raise ValueError('Only the current active cycle_v1 season can be corrected')
            receipt = db.execute(select(AdminAuditLog).where(
                AdminAuditLog.action == self.action, AdminAuditLog.entity_type == self.entity_type,
                AdminAuditLog.entity_id == command_id.strip(),
                AdminAuditLog.before_data['season_id'].as_integer() == season_id)).scalar_one_or_none()
            if receipt is not None:
                if receipt.after_data['command'] != payload:
                    raise EconomyConflict('Command ID was already used for a different correction')
                return {key: value for key, value in receipt.after_data.items() if key != 'command'}
            self._clan(db, clan_id)
            state = self._state(db, season_id, clan_id)
            if state.revision != expected_revision:
                raise EconomyConflict('Economy revision changed; reload the treasury')
            now = clock.utc_now()
            self._require_snapshot(db, state, cycles, now)
            CycleIncomeService().accrue(db, state_id=state.id, now=now)
            before = self._serialize(state)
            CycleEconomyStore._write(db, state, wallet=values)
            result = self._serialize(state)
            AdminAuditService().record(db, actor_user_id=actor_id, action=self.action,
                entity_type=self.entity_type, entity_id=command_id.strip(),
                before_data=before, after_data={**result, 'command': payload}, reason=reason.strip())
            db.flush()
            return result
