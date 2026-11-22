from datetime import datetime, timezone
from types import SimpleNamespace

from app.models.match import Match, MatchParticipant
from app.models.external_identity import ExternalPlayerIdentity
from app.models.user import User
from app.services.cycle_battle_match_view import battle_match_summaries


def test_summary_links_current_names_by_uuid_and_preserves_both_teams(db):
    user = User(username='New name', display_name='Current name')
    db.add(user); db.flush()
    db.add(ExternalPlayerIdentity(user_id=user.id, source='bfmeladder', external_uuid='uuid-a', current_nickname='Current name'))
    match = Match(match_id='arena-demo', winner_player='Old name', loser_player='Opponent',
                  winner_faction='Gondor', loser_faction='Mordor', match_date=datetime(2026, 10, 29, tzinfo=timezone.utc),
                  map_name='Fords', game_mode='2 vs 2', duration='00:20:00', patch_name='Ennorath')
    db.add(match); db.flush()
    for name, uuid, team, winner, observer in [('Old name', 'uuid-a', 1, True, False), ('Ally', 'uuid-b', 1, True, False),
                                               ('Opponent', 'uuid-c', 2, False, False), ('Spectator', 'uuid-d', 3, False, True)]:
        db.add(MatchParticipant(match_id=match.id, nickname=name, player_uuid=uuid, team=team, is_winner=winner, is_observer=observer))
    db.flush()
    rows = [SimpleNamespace(replay_id='bfmeladder:arena-demo', user_id=user.id, calculation={'uuid': 'uuid-a'})]
    result = battle_match_summaries(db, rows)[0]
    assert result['replay_id'] == rows[0].replay_id and result['match_ref'] == 'arena-demo'
    assert result['map_name'] == 'Fords' and result['game_mode'] == '2 vs 2'
    assert len(result['participants']) == 3
    first = next(p for p in result['participants'] if p['user_id'] == user.id)
    assert first['name'] == 'Current name' and first['is_winner'] is True and first['team'] == 1
    assert 'player_uuid' not in first and 'source_payload' not in result


def test_missing_and_foreign_references_do_not_invent_a_match_or_use_database_id(db):
    match = Match(match_id='external-id', winner_player='Winner', loser_player='Loser',
                  winner_faction='Gondor', loser_faction='Mordor', match_date=datetime(2026, 10, 29))
    db.add(match); db.flush()
    rows = [SimpleNamespace(replay_id=value, user_id=999, calculation=None)
            for value in ['bfmeladder:missing', f'bfmeladder:{match.id}', 'foreign:external-id']]
    assert battle_match_summaries(db, rows) == []


def test_legacy_duel_without_participant_rows_uses_recorded_result(db):
    match = Match(match_id='duel', winner_player='Winner', loser_player='Loser',
                  winner_faction='Gondor', loser_faction='Mordor', game_mode='1 vs 1', match_date=datetime(2026, 10, 29))
    db.add(match); db.flush()
    row = SimpleNamespace(replay_id='bfmeladder:duel', user_id=999, calculation=None)
    result = battle_match_summaries(db, [row, row])
    assert len(result) == 1
    assert [(p['name'], p['is_winner']) for p in result[0]['participants']] == [('Winner', True), ('Loser', False)]
    assert result[0]['played_at'].utcoffset().total_seconds() == 0


def test_complete_source_teams_are_used_when_participant_rows_are_missing(db):
    from dataclasses import replace
    from uuid import UUID
    from tests.test_cycle_match_service import match_world
    from tests.test_cycle_arena_ingestion import saved
    from app.services.cycle_match_service import ReplayPlayer
    users, _, _, _, _, replay = match_world(db)
    replay = replace(replay, players=replay.players + (ReplayPlayer(str(UUID(int=99)), 1, None, False, None), ReplayPlayer(str(UUID(int=100)), 2, None, False, None)))
    match = saved(db, replay)
    row = SimpleNamespace(replay_id='bfmeladder:'+match.match_id, user_id=users[2].id, calculation=None)
    participants = battle_match_summaries(db, [row])[0]['participants']
    assert len(participants) == 4
    payload = dict(match.source_payload)
    raw = dict(payload['PublicApiPayload'])
    raw['players'] = [{key: value for key, value in player.items() if key != 'isWinner'} for player in raw['players']]
    payload['PublicApiPayload'] = raw
    match.source_payload = payload
    db.flush()
    assert all(p['is_winner'] is None for p in battle_match_summaries(db, [row])[0]['participants'])


def test_incomplete_legacy_team_match_does_not_turn_into_a_duel(db):
    match = Match(match_id='incomplete-team', winner_player='Winner', loser_player='Loser',
                  winner_faction='Gondor', loser_faction='Mordor', game_mode='2 vs 2', match_date=datetime(2026, 10, 29))
    db.add(match); db.flush()
    row = SimpleNamespace(replay_id='bfmeladder:incomplete-team', user_id=999, calculation=None)
    assert battle_match_summaries(db, [row])[0]['participants'] == []
