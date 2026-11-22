"""Apply a confirmed cycle result once; score review alone cannot transfer land."""

from decimal import Decimal
from hashlib import sha256
import json

from sqlalchemy import func

from app.core.time import as_utc
from app.models.campaign import CampaignRuleSet, CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.clan import Clan
from app.models.cycle_battle import CycleTerritoryBattle, CycleOwnershipCorrection
from app.models.cycle_economy import CycleEconomyState, CycleEconomySnapshot
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.models.user import User
from app.services.campaign_cycle_service import _utc
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.campaign_rule_service import CampaignRuleService
from app.services.clan_level_service import ClanLevelService
from app.services.cycle_battle_service import CycleBattleService
from app.services.cycle_income_service import CycleIncomeService
from app.services.cycle_economy_store import CycleEconomyStore


class CycleOwnershipService:
    @staticmethod
    def _accrue_before_change(db, season_id, now):
        income = CycleIncomeService()
        for state in db.query(CycleEconomyState).filter_by(season_id=season_id).order_by(CycleEconomyState.id):
            income.accrue(db, state_id=state.id, now=now)

    @staticmethod
    def _transfer(db, territory, new_owner, season, now, reason='cycle_result'):
        previous = territory.owner_clan_id
        if previous == new_owner:
            return
        opened = db.query(TerritoryOwnershipHistory).filter_by(territory_id=territory.id, ended_at=None).with_for_update().all()
        for entry in opened:
            entry.ended_at = now
        if previous is not None and not opened:
            db.add(TerritoryOwnershipHistory(territory_id=territory.id, clan_id=previous,
                   started_at=territory.owned_since or season.starts_at, ended_at=now, reason=reason))
        territory.owner_clan_id = new_owner
        territory.owned_since = now if new_owner is not None else None
        if new_owner is not None:
            db.add(TerritoryOwnershipHistory(territory_id=territory.id, clan_id=new_owner,
                   started_at=now, reason=reason))
        # No development reduction or legacy payout-delay reset in this mode.
        db.flush()

    @staticmethod
    def _recalculate(db, clan_id, cycle, rule, now):
        if clan_id is None:
            return
        clan = db.query(Clan).filter_by(id=clan_id).with_for_update().one_or_none()
        if clan is None or clan.is_deleted:
            return
        state = db.query(CycleEconomyState).filter_by(season_id=cycle.season_id, clan_id=clan_id).one_or_none()
        snapshot = db.query(CycleEconomySnapshot).filter_by(cycle_id=cycle.id, state_id=state.id).one_or_none() if state else None
        bonus = sum((Decimal(effect['percent']) for effect in snapshot.effects if effect['effect'] == 'influence'), Decimal(0)) if snapshot else Decimal(0)
        held = db.query(func.sum(Territory.influence_value)).filter_by(owner_clan_id=clan_id).scalar() or 0
        clan.territory_points = int(clan.base_influence or 0) + int(Decimal(held) * (1 + bonus / 100))
        ClanLevelService().evaluate(db, clan, rule_set=CampaignRuleService._snapshot(rule), now=now)

    def apply_result(self, db, *, battle_id, now):
        accounting = CycleBattleService()
        cycle, battle = accounting._locked(db, battle_id)
        if battle.ownership_applied_at is not None:
            return battle
        now = _utc(now)
        if battle.completed_at is None or now < as_utc(battle.completed_at):
            raise ValueError('Confirmed battle calculation is required')
        if any(not done for key, done in cycle.dependencies.items() if key.startswith('interception:')):
            raise ValueError('Interception dependencies are not complete')
        season = db.get(CampaignSeason, cycle.season_id)
        if season is None or season.status != 'active' or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
            raise ValueError('Active cycle season required')
        rule = db.query(CampaignRuleSet).filter_by(version=cycle.rule_version).one_or_none()
        if rule is None:
            raise ValueError('Frozen rule version not found')
        land = db.query(Territory).filter_by(id=battle.territory_id).with_for_update().one()
        if land.owner_clan_id != battle.owner_clan_id:
            raise ValueError('Current owner changed; explicit administrative review required')
        self._accrue_before_change(db, cycle.season_id, now)
        accounting.cycles._bump(db, cycle)
        self._transfer(db, land, battle.winner_clan_id, season, now)
        for clan_id in sorted({s['clan_id'] for s in battle.sides}):
            self._recalculate(db, clan_id, cycle, rule, now)
        battle.ownership_applied_at = now
        db.flush()
        accounting.cycles.complete_dependency(db, cycle_id=cycle.id, key=f'territory:{battle.id}')
        return battle

    @staticmethod
    def _correction_context(db, battle_id, *, lock=False):
        reference = db.get(CycleTerritoryBattle, battle_id)
        if reference is None:
            raise ValueError('Unknown territory battle')
        source = db.get(CampaignCycleRecord, reference.cycle_id)
        if lock:
            cycles = CycleIncomeService._cycles(db, source.season_id)
            # A new cycle can commit while the locking SELECT waits. Its
            # statement snapshot may still contain only the preceding rows.
            latest = db.query(CampaignCycleRecord.id).filter_by(season_id=source.season_id).order_by(CampaignCycleRecord.number.desc()).first()
            if latest is None or latest.id != cycles[-1].id:
                raise CycleConflict('Ownership preview changed during cycle advancement; refresh before confirming')
        else:
            cycles = db.query(CampaignCycleRecord).filter_by(season_id=source.season_id).order_by(CampaignCycleRecord.number).populate_existing().all()
        season_query = db.query(CampaignSeason).filter_by(id=source.season_id)
        battle_query = db.query(CycleTerritoryBattle).filter_by(id=battle_id)
        land_query = db.query(Territory).filter_by(id=reference.territory_id)
        if lock:
            season_query = season_query.with_for_update()
            battle_query = battle_query.with_for_update()
            land_query = land_query.with_for_update()
        season = season_query.populate_existing().one()
        if season.status != 'active' or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
            raise ValueError('Active cycle season required')
        battle = battle_query.populate_existing().one()
        if battle.completed_at is None or battle.ownership_applied_at is None:
            raise ValueError('Confirmed and applied battle result required')
        land = land_query.populate_existing().one()
        history = db.query(TerritoryOwnershipHistory).filter_by(territory_id=land.id).order_by(TerritoryOwnershipHistory.id.desc()).first()
        # Include the latest cycle and history ID to detect owner changes even
        # when the land was subsequently returned to the same clan.
        values = [battle.id, cycles[-1].id, land.id, land.owner_clan_id,
                  as_utc(land.owned_since).isoformat() if land.owned_since else None,
                  history.id if history else None]
        token = sha256(json.dumps(values, separators=(',', ':')).encode('ascii')).hexdigest()
        return season, battle, land, cycles[-1], token

    def preview_correction(self, db, *, battle_id):
        _, battle, land, current, token = self._correction_context(db, battle_id)
        owner = db.get(Clan, land.owner_clan_id) if land.owner_clan_id is not None else None
        choices = db.query(Clan).filter(Clan.id.in_([side['clan_id'] for side in battle.sides]),
            Clan.is_deleted.is_(False), Clan.is_admin_clan.is_(False)).order_by(Clan.id).all()
        return dict(battle_id=battle.id, territory_id=land.id, territory_name=land.name,
                    current_cycle_id=current.id, current_owner_clan_id=land.owner_clan_id,
                    current_owner_name=owner.name if owner and not owner.is_deleted else None,
                    preview_token=token,
                    choices=[dict(clan_id=None, clan_name=None)] + [dict(clan_id=c.id, clan_name=c.name) for c in choices])

    def correct_ownership(self, db, *, battle_id, new_owner_clan_id, preview_token,
                          command_id, actor_user_id, reason, now):
        """Admin-only caller. Apply from now, never rewrite prior cycle outcomes."""
        now = _utc(now)
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise ValueError('A correction reason is required')
        if not isinstance(command_id, str) or not 1 <= len(command_id.strip()) <= 120:
            raise ValueError('A command ID is required')
        if type(actor_user_id) is not int or db.get(User, actor_user_id) is None:
            raise ValueError('Database administrator user ID required')
        reason, command_id = reason.strip(), command_id.strip()
        with CycleEconomyStore._atomic(db):
            season, battle, land, current, token = self._correction_context(db, battle_id, lock=True)
            receipt = db.query(CycleOwnershipCorrection).filter_by(season_id=season.id, command_id=command_id).one_or_none()
            if receipt:
                if (receipt.battle_id, receipt.new_owner_clan_id, receipt.preview_token, receipt.actor_user_id, receipt.reason) != (
                        battle_id, new_owner_clan_id, preview_token, actor_user_id, reason):
                    raise CycleConflict('Ownership command was already used with a different payload')
                return receipt
            if preview_token != token:
                raise CycleConflict('Ownership preview changed; refresh before confirming')
            if now < as_utc(battle.ownership_applied_at) or now < as_utc(current.starts_at):
                raise ValueError('Correction cannot predate the current campaign state')
            if new_owner_clan_id is not None:
                clan = db.query(Clan).filter_by(id=new_owner_clan_id).with_for_update().one_or_none()
                if (type(new_owner_clan_id) is not int or clan is None or clan.is_deleted or clan.is_admin_clan
                        or new_owner_clan_id not in {side['clan_id'] for side in battle.sides}):
                    raise ValueError('Choose an active participant of this battle or neutral land')
            previous = land.owner_clan_id
            if previous == new_owner_clan_id:
                raise ValueError('Territory already has this owner')
            latest_history = db.query(TerritoryOwnershipHistory).filter_by(territory_id=land.id).order_by(TerritoryOwnershipHistory.id.desc()).first()
            if latest_history and now < as_utc(latest_history.started_at):
                raise ValueError('Correction cannot predate ownership history')
            rule = db.query(CampaignRuleSet).filter_by(version=current.rule_version).one_or_none()
            if rule is None:
                raise ValueError('Current rule version not found')
            self._accrue_before_change(db, season.id, now)
            CampaignCycleStore._bump(db, current)
            self._transfer(db, land, new_owner_clan_id, season, now, reason='cycle_admin_correction')
            for clan_id in sorted({value for value in (previous, new_owner_clan_id) if value is not None}):
                self._recalculate(db, clan_id, current, rule, now)
            receipt = CycleOwnershipCorrection(season_id=season.id, battle_id=battle.id,
                current_cycle_id=current.id, territory_id=land.id, previous_owner_clan_id=previous,
                new_owner_clan_id=new_owner_clan_id, actor_user_id=actor_user_id,
                command_id=command_id, preview_token=preview_token, reason=reason, applied_at=now)
            db.add(receipt)
            db.flush()
            return receipt
