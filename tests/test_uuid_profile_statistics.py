import asyncio
from datetime import datetime

from app.api.v1.users import get_player_statistics, get_all_user_matches
from app.api.v1.statistics import get_player_ratings
from app.services.arena_current_rating_service import arena_current_ratings
from app.services.external_identity_service import ExternalIdentityService
from app.services.ladder_service import BFMELadderService
from app.models.user import User
from app.models.external_identity import ExternalPlayerIdentity
from app.models.match import Match, MatchParticipant


def test_profile_owns_uuid_after_rename_and_excludes_namesake(db, monkeypatch):
    user = User(username='InternalLogin', display_name='NewName', hashed_password='unused')
    db.add(user)
    db.flush()
    db.add(ExternalPlayerIdentity(user_id=user.id, source='bfmeladder',
        external_uuid='player-uuid', current_nickname='NewName', verification_status='verified'))
    for name, uuid, won in [('NeverSeenAlias', 'player-uuid', True),
                             ('NewName', 'other-uuid', False)]:
        match = Match(match_id=name, winner_player=name, winner_faction='Gondor',
                      loser_player='Enemy', loser_faction='Mordor',
                      match_date=datetime(2026, 10, 10), rating_patch_family='ennorath')
        match.participants = [MatchParticipant(nickname=name, player_uuid=uuid,
            faction='Gondor', is_winner=won, elo=1250)]
        db.add(match)
    db.commit()
    stats = asyncio.run(get_player_statistics('NewName', db))
    assert stats['total_matches'] == 1
    assert stats['wins'] == 1
    assert stats['current_elo']['ennorath'] == 1250
    matches = asyncio.run(get_all_user_matches('NewName', db))
    assert [row['id'] for row in matches] == ['NeverSeenAlias']


def test_live_uuid_rating_exists_without_local_history(db, monkeypatch):
    user = User(username='Login', display_name='Renamed', hashed_password='unused', is_claimed=True)
    db.add(user)
    db.flush()
    db.add(ExternalPlayerIdentity(user_id=user.id, source='bfmeladder',
        external_uuid='stable-uuid', current_nickname='Renamed', verification_status='verified'))
    db.commit()

    async def ladder(patch):
        return [('unknown-new-name', 'stable-uuid', 1312 if patch == 'ennorath' else 1074)]

    monkeypatch.setattr(arena_current_ratings, 'fetch_patch', ladder)
    stats = asyncio.run(get_player_statistics('Renamed', db))
    assert stats['total_matches'] == 0
    assert stats['current_elo'] == {'ennorath': 1312, 'patch_202': 1074}
    ratings = asyncio.run(get_player_ratings(patch='ennorath',sort='elo_desc', search=None,
        min_elo=None,max_elo=None,page=1,limit=25,current_user=user,db=db))
    assert ratings['players'][0]['elo'] == 1312
    assert ratings['players'][0]['username'] == 'Renamed'


def test_rating_groups_different_names_by_uuid_not_alias(db):
    viewer = User(username='Viewer', hashed_password='unused', is_claimed=False)
    db.add(viewer)
    for hour, nickname in enumerate(['OldName', 'NewName']):
        match = Match(match_id=nickname, winner_player=nickname,winner_faction='Gondor',
            loser_player='Enemy',loser_faction='Mordor',match_date=datetime(2026,10,10,hour),
            rating_patch_family='ennorath')
        match.participants = [MatchParticipant(nickname=nickname,player_uuid='stable-uuid',
            faction='Gondor',is_winner=True,elo=1200 + hour)]
        db.add(match)
    db.commit()
    ratings = asyncio.run(get_player_ratings(patch='ennorath',sort='elo_desc',search=None,
        min_elo=None,max_elo=None,page=1,limit=25,current_user=viewer,db=db))
    assert len(ratings['players']) == 1
    assert ratings['players'][0]['elo'] == 1201
    assert ratings['players'][0]['matches'] == 2


def test_missing_replay_uuid_is_restored_from_unique_identity(db):
    user = User(username='Login', display_name='NewName', hashed_password='unused')
    db.add(user)
    db.flush()
    identity = ExternalPlayerIdentity(user_id=user.id, source='bfmeladder',
        external_uuid='stable-uuid', current_nickname='NewName', verification_status='verified')
    db.add(identity)
    match = Match(match_id='legacy',winner_player='NewName',winner_faction='Gondor',
        loser_player='Enemy',loser_faction='Mordor',match_date=datetime(2026,10,10))
    match.participants = [MatchParticipant(nickname='NewName',is_winner=True)]
    db.add(match)
    db.commit()
    BFMELadderService()._backfill_known_match_identity(db, match, {'Players': []})
    assert match.winner_player_uuid == 'stable-uuid'
    assert match.participants[0].player_uuid == 'stable-uuid'
    other = User(username='OtherLogin',hashed_password='unused')
    db.add(other)
    db.flush()
    db.add(ExternalPlayerIdentity(user_id=other.id,source='bfmeladder',
        external_uuid='other-uuid',current_nickname='NewName'))
    db.commit()
    assert ExternalIdentityService().uuid_for_known_nickname(db,'NewName') is None


def test_unverified_legacy_elo_is_not_presented_as_current_rating(db):
    viewer=User(username='Viewer',hashed_password='unused',is_claimed=False)
    match=Match(match_id='unverified',winner_player='Player',winner_faction='Gondor',
        loser_player='Enemy',loser_faction='Mordor',match_date=datetime(2026,10,10),
        rating_patch_family='ennorath',source_payload={
            'rating_unverified_players':[{'uuid':'player-uuid','nickname':'Player'}]})
    match.participants=[MatchParticipant(nickname='Player',player_uuid='player-uuid',
        is_winner=True,elo=1000)]
    db.add_all([viewer,match])
    db.commit()
    ratings=asyncio.run(get_player_ratings(patch='ennorath',sort='elo_desc',search='Player',
        min_elo=None,max_elo=None,page=1,limit=25,current_user=viewer,db=db))
    assert ratings['players'][0]['elo'] is None
    assert ratings['players'][0]['rated'] is False
    assert match.participants[0].elo == 1000
