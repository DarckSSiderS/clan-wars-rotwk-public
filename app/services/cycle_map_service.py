"""Viewer-safe current-cycle map projection; never initializes or commits."""
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord, CampaignCyclePlan
from app.models.clan import Clan, ClanMember
from app.models.cycle_battle import CycleTerritoryBattle
from app.models.cycle_reinforcement_state import CycleReinforcementState
from app.models.cycle_economy import CycleTerritoryUpgrade
from app.models.cycle_income import CycleTerritoryProfile
from app.models.territory import Territory
from app.services import cycle_economy as economy
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_battle_service import CycleBattleService
from app.services.cycle_reinforcement_store import CycleReinforcementStore
from app.services.cycle_dispatch_route_service import CycleDispatchRouteService


class CycleMapService:
    @staticmethod
    def _territories(db, season_id):
        upgrades = {row.territory_id: row.levels for row in db.query(CycleTerritoryUpgrade).filter_by(season_id=season_id)}
        result = []
        profiles = db.query(CycleTerritoryProfile).join(Territory).filter(
            CycleTerritoryProfile.season_id == season_id, Territory.is_playable.is_(True)
        ).order_by(CycleTerritoryProfile.territory_id)
        for profile in profiles:
            levels = {branch: upgrades.get(profile.territory_id, {}).get(branch, 0) for branch in economy.UPGRADES}
            branch = 'mithril' if profile.profile_material == 'mithril' else 'profile'
            income = economy.territory_income(economy.Resources(**profile.base), profile.profile_material,
                gold_level=levels['gold'], profile_level=levels[branch])
            result.append(dict(territory_id=profile.territory_id, profile_material=profile.profile_material,
                daily_income={key: str(getattr(income, key)) for key in economy.RESOURCE_NAMES},
                levels=levels, max_level=3))
        return result

    def read(self, db, *, cycle_id, actor_user_id, now):
        season = db.query(CampaignSeason).filter_by(status='active').order_by(CampaignSeason.number.desc()).first()
        cycle = db.query(CampaignCycleRecord).filter_by(season_id=season.id).order_by(CampaignCycleRecord.number.desc()).first() if season else None
        if cycle is None or cycle.id != cycle_id or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
            raise ValueError('Current active cycle required')
        timeline = CampaignCycleStore.timeline(cycle)
        phase = timeline.phase_at(now).value if now >= timeline.starts_at else 'scheduled'
        memberships = db.query(ClanMember).filter_by(user_id=actor_user_id).all()
        clan = db.get(Clan, memberships[0].clan_id) if len(memberships) == 1 else None
        clan_id = clan.id if clan and not clan.is_deleted else None
        result = dict(cycle_id=cycle_id, phase=phase, server_time=now, ready=False,
                      clan_id=clan_id, can_command=False, command_deadline=None, revision=None,
                      battles=[], dispatches=[], ambushes=[], requests=[], help_targets=[], allied_targets=[],
                      attack_routes=[], clans=[],
                      territories=self._territories(db, season.id))
        row = db.query(CycleReinforcementState).filter_by(cycle_id=cycle_id).one_or_none()
        if phase not in {'battle', 'replay_loading', 'settlement'} or row is None or not cycle.battles_registered or cycle.orders_frozen_at is None:
            return result
        store = CycleReinforcementStore()
        state, bindings = store._unpack(row, cycle)
        view = store._view(row, state, bindings, clan_id)
        clan_rows={c.id:c for c in db.query(Clan)}
        names={t.id:t.name for t in db.query(Territory).filter_by(is_playable=True)}
        visible_clans=set()
        def clan_info(key):
            if key is not None:
                visible_clans.add(key)
            item=clan_rows.get(key)
            return dict(id=key,name=item.name if item and not item.is_deleted else None,
                        map_color=item.map_color if item and not item.is_deleted else None)
        CycleDispatchRouteService.project(db, cycle_id=cycle_id, view=view)
        result.update(ready=True, revision=row.revision, ambushes=view['ambushes'],
                      requests=[q for q in view['requests'] if q['dispatch_id'] is None])
        for request in result['requests']:
            recipient=clan_info(request['recipient_clan_id'])
            request.update(clan_name=recipient['name'],map_color=recipient['map_color'],
                           territory_name=names.get(request['territory_id']))
        # Frozen member IDs are already public only for revealed movements/ambushes.
        for item, dispatch in zip(view['dispatches'], state.dispatches):
            sender=clan_info(item['sender_clan_id'])
            recipient=clan_info(item['recipient_clan_id'])
            result['dispatches'].append({**item, 'sender_clan_name':sender['name'],
                                         'recipient_clan_name':recipient['name'],
                                         'territory_name':names.get(item['territory_id']),
                                         'player_count':len(item['player_user_ids']),
                                         'interception_at': dispatch.interception_at,
                                         'interception_ends_at': dispatch.interception_ends_at})
        if clan_id is not None:
            own = store.context(db, cycle_id=cycle_id, viewer_clan_id=clan_id, actor_user_id=actor_user_id, now=now)
            result.update(can_command=own['can_command'], command_deadline=own['command_deadline'],
                          help_targets=own['help_targets'], allied_targets=own['allied_targets'])
        for battle in db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle_id).order_by(CycleTerritoryBattle.id):
            scores = CycleBattleService().scores(db, battle.id)
            sides = []
            for side in battle.sides:
                owner=clan_info(side['clan_id'])
                sides.append(dict(clan_id=side['clan_id'],clan_name=owner['name'],map_color=owner['map_color'],
                                  role='defender' if side['clan_id']==battle.owner_clan_id else 'attacker',
                                  player_count=len(side['user_ids']),score=str(scores[side['clan_id']])))
            attackers=[side for side in sides if side['role']=='attacker']
            status=('contested' if len(attackers)>1 else 'neutral_claim') if battle.owner_clan_id is None else ('contested' if attackers else 'defense')
            result['battles'].append(dict(battle_id=battle.id,territory_id=battle.territory_id,
                territory_name=names.get(battle.territory_id),owner_clan_id=battle.owner_clan_id,
                owner_clan_name=clan_info(battle.owner_clan_id)['name'],status=status,
                completed=bool(battle.completed_at),sides=sides))
        public_targets={b['territory_id']:{s['clan_id'] for s in b['sides']} for b in result['battles']}
        grouped={}
        for plan in db.query(CampaignCyclePlan).filter_by(cycle_id=cycle_id):
            if plan.frozen_at is None:
                continue
            for order in plan.orders:
                target=order.get('territory_id')
                if order['kind']=='attack' and plan.clan_id in public_targets.get(target,set()):
                    key=(plan.clan_id,order.get('source_id'),target,order.get('route','land'))
                    grouped.setdefault(key,set()).add(order['user_id'])
        for (attacker,source,target,transport),players in sorted(grouped.items(),key=lambda item:(item[0][0],item[0][1] or 0,item[0][2],item[0][3])):
            clan_data=clan_info(attacker)
            result['attack_routes'].append(dict(clan_id=attacker,clan_name=clan_data['name'],map_color=clan_data['map_color'],
                source_territory_id=source,source_territory_name=names.get(source),
                target_territory_id=target,target_territory_name=names.get(target),route=transport,player_count=len(players)))
        result['clans']=[clan_info(key) for key in sorted(visible_clans)]
        return result
