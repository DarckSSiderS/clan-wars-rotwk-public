"""New-cycle battle accounting. Caller owns the transaction and admin checks."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

from app.core.time import as_utc
from app.models.campaign_cycle import CampaignCyclePlan
from app.models.clan import Clan
from app.models.cycle_battle import CycleTerritoryBattle, CycleMatchContribution, CycleScoreAdjustment
from app.services.campaign_cycle_service import _utc
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_scoring import _decimal, territory_winner


def _stored_points(value):
    value = _decimal(value)
    if abs(value) >= Decimal('1e16'):
        raise ValueError('Score exceeds storage precision')
    try:
        return value.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_EVEN)
    except InvalidOperation as error:
        raise ValueError('Invalid score precision') from error


class CycleBattleService:
    def __init__(self):
        self.cycles = CampaignCycleStore()

    def _locked(self, db, battle_id):
        reference = db.get(CycleTerritoryBattle, battle_id)
        if reference is None:
            raise ValueError('Unknown territory battle')
        cycle = self.cycles._locked(db, reference.cycle_id)
        battle = db.query(CycleTerritoryBattle).filter_by(id=battle_id).with_for_update().populate_existing().one()
        return cycle, battle

    def create_from_orders(self, db, *, cycle_id):
        cycle = self.cycles._locked(db, cycle_id)
        if cycle.orders_frozen_at is None:
            raise ValueError('Orders must be frozen before battle creation')
        plans = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle_id).all()
        targets = {}
        for plan in plans:
            if plan.frozen_at is None:
                raise ValueError('Every plan must be frozen')
            for order in plan.orders:
                if order['kind'] in {'attack', 'defend'}:
                    targets.setdefault(order['territory_id'], {}).setdefault(plan.clan_id, []).append(order['user_id'])
        owners = {row['id']: row['owner_clan_id'] for row in cycle.planning_snapshot}
        for territory_id, sides in sorted(targets.items()):
            existing = db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle_id, territory_id=territory_id).one_or_none()
            if existing:
                continue
            owner = owners[territory_id]
            if owner is not None:
                sides.setdefault(owner, [])
            row = CycleTerritoryBattle(cycle_id=cycle_id, territory_id=territory_id, owner_clan_id=owner,
                                      sides=[{'clan_id': clan_id, 'user_ids': sorted(users)}
                                             for clan_id, users in sorted(sides.items())])
            self.cycles._bump(db, cycle)
            db.add(row)
            db.flush()
            self.cycles.register_dependency(db, cycle_id=cycle_id, key=f'territory:{row.id}')
        if not cycle.battles_registered:
            self.cycles._bump(db, cycle)
            cycle.battles_registered = True
            db.flush()
        return db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle_id).order_by(CycleTerritoryBattle.territory_id).all()

    @staticmethod
    def _side(battle, clan_id):
        side = next((s for s in battle.sides if s['clan_id'] == clan_id), None)
        if side is None:
            raise ValueError('Clan is not a battle side')
        return side

    def record_contribution(self, db, *, battle_id, replay_id, user_id, clan_id, points, reason):
        cycle, battle = self._locked(db, battle_id)
        if not replay_id or len(replay_id) > 120 or not reason or len(reason) > 500:
            raise ValueError('Replay ID and bounded reason are required')
        points = _stored_points(points)
        side = self._side(battle, clan_id)
        if user_id not in side['user_ids']:
            raise ValueError('Player is not assigned to this side')
        existing = db.query(CycleMatchContribution).filter_by(battle_id=battle_id, replay_id=replay_id, user_id=user_id).one_or_none()
        if existing:
            if existing.clan_id != clan_id or existing.points != points:
                raise ValueError('Conflicting replay contribution requires explicit review')
            return existing
        if battle.completed_at is not None:
            raise ValueError('Late matches require explicit administrative review')
        self.cycles._bump(db, cycle)
        row = CycleMatchContribution(battle_id=battle_id, replay_id=replay_id, user_id=user_id,
                                    clan_id=clan_id, points=points, counted=reason == 'counted', reason=reason)
        db.add(row)
        db.flush()
        return row

    def scores(self, db, battle_id):
        battle = db.get(CycleTerritoryBattle, battle_id)
        if battle is None:
            raise ValueError('Unknown battle')
        scores = {s['clan_id']: Decimal(0) for s in battle.sides}
        for row in db.query(CycleMatchContribution).filter_by(battle_id=battle_id, counted=True):
            if row.clan_id in scores:
                scores[row.clan_id] += row.points
        for row in db.query(CycleScoreAdjustment).filter_by(battle_id=battle_id):
            if row.clan_id in scores:
                scores[row.clan_id] += row.points
        return scores

    def _project(self, db, battle):
        scores = self.scores(db, battle.id)
        active = {clan.id for clan in db.query(Clan).filter(Clan.id.in_(scores), Clan.is_deleted.is_(False))}
        owner = battle.owner_clan_id if battle.owner_clan_id in active else None
        return territory_winner({clan_id: score for clan_id, score in scores.items() if clan_id in active}, owner_clan_id=owner)

    def finalize(self, db, *, battle_id, completed_at):
        cycle, battle = self._locked(db, battle_id)
        if battle.completed_at is not None:
            return battle
        completed_at = _utc(completed_at)
        if completed_at < self.cycles.timeline(cycle).replay_deadline or cycle.import_verified_at is None:
            raise ValueError('Replay loading and successful import are required')
        if completed_at < as_utc(cycle.import_verified_at):
            raise ValueError('Settlement cannot precede import verification')
        self.cycles._bump(db, cycle)
        battle.winner_clan_id = battle.recalculated_winner_clan_id = self._project(db, battle)
        battle.completed_at = completed_at
        db.flush()
        return battle

    @staticmethod
    def _reason(reason):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise ValueError('A nonempty reason up to 500 characters is required')
        return reason.strip()

    def review_contribution(self, db, *, battle_id, replay_id, user_id, counted, actor_user_id, reason):
        reason = self._reason(reason)
        cycle, battle = self._locked(db, battle_id)
        row = db.query(CycleMatchContribution).filter_by(battle_id=battle_id, replay_id=replay_id, user_id=user_id).one_or_none()
        if row is None:
            raise ValueError('Unknown match contribution')
        self.cycles._bump(db, cycle)
        row.counted, row.review_reason, row.reviewed_by_user_id = bool(counted), reason, actor_user_id
        db.flush()
        if battle.completed_at is not None:
            battle.recalculated_winner_clan_id = self._project(db, battle)
        return row

    def adjust(self, db, *, battle_id, clan_id, amount, command_id, actor_user_id, reason):
        reason = self._reason(reason)
        amount = _stored_points(amount)
        if not isinstance(command_id, str) or not command_id.strip() or len(command_id) > 120:
            raise ValueError('A stable command ID is required')
        cycle, battle = self._locked(db, battle_id)
        self._side(battle, clan_id)
        existing = db.query(CycleScoreAdjustment).filter_by(battle_id=battle_id, command_id=command_id).one_or_none()
        if existing:
            if (existing.clan_id, existing.points, existing.actor_user_id, existing.reason) != (clan_id, amount, actor_user_id, reason):
                raise ValueError('Command ID was already used for a different adjustment')
            return existing
        self.cycles._bump(db, cycle)
        row = CycleScoreAdjustment(battle_id=battle_id, clan_id=clan_id, points=amount,
                                   command_id=command_id, actor_user_id=actor_user_id, reason=reason)
        db.add(row)
        db.flush()
        if battle.completed_at is not None:
            battle.recalculated_winner_clan_id = self._project(db, battle)
        return row
