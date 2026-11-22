from datetime import timedelta

from app.models.campaign_cycle import CampaignCyclePlan, CampaignCyclePlanRevision, CycleScoutRequest
from app.models.cycle_economy import CycleEconomyState
from app.models.territory import Territory
from app.models.user import User
from app.models.clan import ClanMember
from app.models.campaign import CampaignSeason
from app.services.campaign_cycle_service import CyclePhase, _utc
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_economy import Resources, debit
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_plan_service import CyclePlanService


class CycleReconnaissanceService:
    @staticmethod
    def available_players(db, *, cycle_id, clan_id):
        assigned = {o['user_id'] for plan in db.query(CampaignCyclePlan).filter_by(cycle_id=cycle_id)
                    for o in plan.orders}
        blocked = assigned | CyclePlanService.scouting_user_ids(db, cycle_id)
        users = db.query(User).join(ClanMember, ClanMember.user_id == User.id).filter(
            ClanMember.clan_id == clan_id, User.is_active.is_(True)).order_by(User.id).all()
        identities = CyclePlanService._identity_snapshot(db, [user.id for user in users])
        return [dict(user_id=u.id, name=u.display_name or u.username, external_uuid=identities[str(u.id)]['uuid'])
                for u in users if u.id not in blocked and str(u.id) in identities]

    def request(self, db, *, cycle_id, clan_id, territory_id, actor_user_id, expected_revision, now, scout_user_id=None):
        cycle = CampaignCycleStore()._locked(db, cycle_id)
        CyclePlanService._permission(db, clan_id, actor_user_id, edit=True)
        previous = db.query(CycleScoutRequest).filter_by(cycle_id=cycle_id, clan_id=clan_id).one_or_none()
        if previous:
            if previous.territory_id != territory_id or previous.scout_user_id != scout_user_id:
                raise ValueError('The paid scouting target and player cannot be changed')
            return previous
        now = _utc(now)
        timeline = CampaignCycleStore.timeline(cycle)
        season = db.get(CampaignSeason, cycle.season_id)
        if season is None or season.status != 'active' or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
            raise ValueError('An active cycle season is required')
        if timeline.phase_at(now) != CyclePhase.PREPARATION or now >= timeline.battle_at - timedelta(hours=6):
            raise ValueError('Scouting must be ordered before the six-hour cutoff')
        territory = db.get(Territory, territory_id)
        if territory is None or not territory.is_playable:
            raise ValueError('Unknown playable territory')
        if type(scout_user_id) is not int or scout_user_id <= 0:
            raise ValueError('One free verified scout player is required')
        scout = next((p for p in self.available_players(db, cycle_id=cycle_id, clan_id=clan_id)
                      if p['user_id'] == scout_user_id), None)
        if scout is None:
            raise ValueError('Scout must be a free active verified clan member')
        state = db.query(CycleEconomyState).filter_by(season_id=cycle.season_id, clan_id=clan_id).one_or_none()
        if state is None:
            raise ValueError('Initialize seasonal economy first')
        economy = CycleEconomyStore()
        state = economy._state(db, state.id, expected_revision)
        balance = debit(economy.balance(state), Resources(gold=200))
        CampaignCycleStore._bump(db, cycle)
        economy._write(db, state, wallet=economy._wallet(balance))
        row = CycleScoutRequest(cycle_id=cycle_id, clan_id=clan_id, territory_id=territory_id,
                               actor_user_id=actor_user_id, requested_at=now,
                               scout_user_id=scout_user_id, scout_uuid=scout['external_uuid'])
        db.add(row)
        db.flush()
        return row

    def report(self, db, *, request_id, actor_user_id, now):
        row = db.get(CycleScoutRequest, request_id)
        if row is None:
            raise ValueError('Unknown scouting request')
        CyclePlanService._permission(db, row.clan_id, actor_user_id)
        cycle = CampaignCycleStore()._locked(db, row.cycle_id)
        cutoff = CampaignCycleStore.timeline(cycle).battle_at - timedelta(hours=6)
        if _utc(now) < cutoff:
            return None
        if row.report is not None:
            return dict(row.report)
        revisions = db.query(CampaignCyclePlanRevision, CampaignCyclePlan.clan_id).join(
            CampaignCyclePlan, CampaignCyclePlan.id == CampaignCyclePlanRevision.plan_id).filter(
                CampaignCyclePlan.cycle_id == row.cycle_id,
                CampaignCyclePlan.clan_id != row.clan_id,
                CampaignCyclePlanRevision.saved_at <= cutoff,
            ).order_by(CampaignCyclePlanRevision.saved_at, CampaignCyclePlanRevision.revision).all()
        latest = {clan_id: revision.orders for revision, clan_id in revisions}
        counts = [len({order['user_id'] for order in orders if order['kind'] in ('attack', 'defend')
                       and order['territory_id'] == row.territory_id}) for orders in latest.values()]
        payload = {'enemy_squads': sorted((size for size in counts if size), reverse=True)}
        CampaignCycleStore._bump(db, cycle)
        row.report = payload
        db.flush()
        return dict(payload)
