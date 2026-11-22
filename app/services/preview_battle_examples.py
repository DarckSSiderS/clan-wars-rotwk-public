"""Manually invoked synthetic matches for the strictly isolated marked preview."""

from datetime import timedelta

from app.models.cycle_battle import CycleTerritoryBattle, CycleMatchContribution
from app.models.external_identity import ExternalPlayerIdentity
from app.models.match import Match, MatchParticipant
from app.models.user import User
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_match_service import CycleMatchService, ReplayFacts, ReplayPlayer
from app.services.preview_scenario_service import _database, _context


def add_preview_battle_examples(database):
    from scripts.seed_campaign_preview import _backup

    with _database(database, write=True) as (path, db, connection):
        _, report, cycle = _context(db)
        if not cycle.orders_frozen_at or not cycle.battles_registered:
            raise ValueError('Reveal the demo cycle before adding example matches')
        demo_ids = {c['id'] for c in report['clans']}
        candidates = db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle.id).order_by(CycleTerritoryBattle.id).all()
        battle = next((b for b in candidates if len(b.sides) >= 2 and all(s['clan_id'] in demo_ids and len(s['user_ids']) >= 2 for s in b.sides[:2])), None)
        if battle is None or battle.completed_at:
            raise ValueError('An unsettled demo battle with two players on each side is required')
        prefix = f'demo-preview-cycle-{cycle.id}-battle-{battle.id}-'
        keys = [prefix + kind for kind in ('duel', 'team', 'short')]
        existing = db.query(Match).filter(Match.match_id.in_(keys)).all()
        if existing:
            if len(existing) != len(keys) or not all((m.source_payload or {}).get('preview_fixture') for m in existing):
                raise ValueError('Conflicting or incomplete demo examples; refusing to overwrite')
            return dict(created=0, cycle_id=cycle.id, battle_id=battle.id, territory_id=battle.territory_id)
        sides = [side['user_ids'][:2] for side in battle.sides[:2]]
        ids = set(sides[0] + sides[1])
        demo_users = {uid for c in report['clans'] for uid in c['member_user_ids']}
        if not ids <= demo_users:
            raise ValueError('Synthetic demo players required')
        users = {u.id: u for u in db.query(User).filter(User.id.in_(ids))}
        identities = {i.user_id: i for i in db.query(ExternalPlayerIdentity).filter(ExternalPlayerIdentity.user_id.in_(ids), ExternalPlayerIdentity.source == 'bfmeladder')}
        if set(identities) != ids:
            raise ValueError('All demo players need UUID identities')
        backup = _backup(path, label='preview-battle-examples')
        start = CampaignCycleStore.timeline(cycle).battle_at
        counts = dict(counted=0, rejected=0)
        for index, kind in enumerate(('duel', 'team', 'short')):
            groups = sides if kind == 'team' else [[side[0]] for side in sides]
            winner = 2 if kind == 'team' else 1
            duration = 45 if kind == 'short' else 1200 + index * 300
            played = start + timedelta(minutes=10 + index * 35)
            winning_user = users[groups[winner-1][0]]
            losing_user = users[groups[2-winner][0]]
            match = Match(match_id=keys[index], winner_player=winning_user.display_name or winning_user.username,
                          loser_player=losing_user.display_name or losing_user.username,
                          winner_player_uuid=identities[winning_user.id].external_uuid,
                          loser_player_uuid=identities[losing_user.id].external_uuid,
                          winner_faction='Gondor', loser_faction='Mordor', match_date=played,
                          duration=f'00:{duration//60:02d}:{duration%60:02d}', game_mode='2 vs 2' if kind == 'team' else '1 vs 1',
                          map_name=['Fords of Isen', 'Buckland', 'Brandy Hills'][index], patch_name='Ennorath',
                          rating_patch_family='ennorath', is_valid=True,
                          source_payload={'preview_fixture': True, 'description': 'Synthetic preview match; never imported from Arena'})
            db.add(match); db.flush()
            players = []
            for team, user_ids in enumerate(groups, start=1):
                for user_id in user_ids:
                    identity, user = identities[user_id], users[user_id]
                    db.add(MatchParticipant(match_id=match.id, nickname=user.display_name or user.username,
                        player_uuid=identity.external_uuid, team=team, is_winner=team == winner, is_observer=False,
                        faction='Gondor' if team == 1 else 'Mordor', elo=1100))
                    players.append(ReplayPlayer(identity.external_uuid, team, 1100, True, 'ennorath'))
            db.flush()
            facts = ReplayFacts(replay_id=match.match_id, source='bfmeladder', patch_family='ennorath', ranked=True,
                                started_at=played, finished_at=played+timedelta(seconds=duration), players=tuple(players), winning_team=winner)
            contributions = CycleMatchService().process(db, battle_id=battle.id, replay=facts)
            for row in contributions:
                counts['counted' if row.counted else 'rejected'] += 1
            if kind != 'short' and not any(row.counted for row in contributions):
                raise ValueError('Demo matches were rejected by real scoring; examples rolled back')
        if connection.exec_driver_sql('PRAGMA foreign_key_check').first():
            raise ValueError('Foreign-key check failed')
        db.flush()
        assert db.query(CycleMatchContribution).filter_by(battle_id=battle.id).count() >= 8
        connection.commit()
        return dict(created=3, cycle_id=cycle.id, battle_id=battle.id, territory_id=battle.territory_id, backup=str(backup), **counts)
