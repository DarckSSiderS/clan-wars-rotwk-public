from datetime import timedelta
from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord, CycleScoutRequest
from app.models.clan import ClanMember
from app.models.cycle_economy import CycleEconomyState
from app.models.cycle_startup import CycleStartup
from app.models.territory import Territory
from app.models.user import User
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_plan_service import CyclePlanService
from app.services.cycle_startup_service import CycleStartupService
from app.services.cycle_reconnaissance_service import CycleReconnaissanceService


class CyclePreparationService:
    def read(self, db, *, cycle_id, clan_id, actor_id, now):
        clan = CyclePlanService._permission(db, clan_id, actor_id)
        # Serialize with claim/qualify before either path locks clans/startup rows.
        cycle = CampaignCycleStore()._locked(db, cycle_id)
        season = db.get(CampaignSeason, cycle.season_id)
        if (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
            raise ValueError('Cycle season required')
        timeline = CampaignCycleStore.timeline(cycle)
        phase = timeline.phase_at(now).value if now >= timeline.starts_at else 'scheduled'
        member = db.query(ClanMember).filter_by(clan_id=clan_id, user_id=actor_id).one()
        user = db.get(User, actor_id)
        onboarded = bool(user.onboarding_completed_at and season.status == 'active')
        commander = onboarded and (clan.leader_id == actor_id or member.is_warlord)
        wallet = db.query(CycleEconomyState).filter_by(season_id=season.id, clan_id=clan_id).one_or_none()
        request = db.query(CycleScoutRequest).filter_by(cycle_id=cycle_id, clan_id=clan_id).one_or_none()
        cutoff = timeline.battle_at - timedelta(hours=6)
        report = CycleReconnaissanceService().report(db, request_id=request.id, actor_user_id=actor_id, now=now) if request else None
        players = CycleReconnaissanceService.available_players(db, cycle_id=cycle_id, clan_id=clan_id) if commander and not request else []
        scout_user = db.get(User, request.scout_user_id) if request and request.scout_user_id else None
        unavailable = ('already_requested' if request else 'no_permission' if not commander else
            'outside_preparation' if phase != 'preparation' else 'cutoff_passed' if now >= cutoff else
            'economy_missing' if not wallet else 'no_free_players' if not players else None)
        result = dict(cycle_id=cycle_id, clan_id=clan_id, clan_name=clan.name, phase=phase, server_time=now,
            scout=dict(price='200', cutoff=cutoff, can_request=bool(commander and players and phase == 'preparation' and now < cutoff and wallet and request is None),
                players=players, unavailable_reason=unavailable, wallet_revision=wallet.revision if wallet else None,
                request=dict(id=request.id, territory_id=request.territory_id, scout_user_id=request.scout_user_id,
                    scout_uuid=request.scout_uuid, scout_name=(scout_user.display_name or scout_user.username) if scout_user else None) if request else None, report=report),
            startup=dict(ready=False, can_claim=False), territories=[])
        lands = db.query(Territory).filter_by(is_playable=True).order_by(Territory.id).all()
        result['territories'] = [dict(id=t.id, name=t.name, owner_clan_id=t.owner_clan_id, port=bool(t.has_port), fortress=t.is_great_stronghold) for t in lands]
        start = db.get(CycleStartup, season.id)
        if start is None or start.cycle_id != cycle_id:
            return result
        rows, members, planned = CycleStartupService()._projection(db, start, now)
        virtual = {t.id: t.owner_clan_id for t in CycleStartupService().selection_world(db, season, start, lands, rows)}
        for territory in result['territories']:
            territory['selection_owner_clan_id'] = virtual[territory['id']]
        row = rows.get(clan_id)
        provisional = next((p for p in planned if p['clan_id'] == clan_id), None)
        eligible = bool(row and (row.initial_owned or row.slot is not None)) or provisional is not None
        if row and not row.initial_owned and row.slot is not None:
            try:
                CycleStartupService._current_four(row, members)
            except ValueError:
                eligible = False
        result['startup'] = dict(ready=True, deadline=as_utc(start.deadline), revision=row.revision if row else 1,
            status=row.status if row else 'pending', selected_lands=list(row.selected_lands) if row else [],
            initial_owned=list(row.initial_owned) if row else [], can_claim=bool(onboarded and clan.leader_id == actor_id and eligible
                and (row is None or row.status == 'pending') and start.expired_at is None and as_utc(start.starts_at) <= now < as_utc(start.deadline)))
        return result
