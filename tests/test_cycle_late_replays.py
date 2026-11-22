"""Поздние реплеи видны администратору без изменения завершённых результатов."""

from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import event

from app.models.cycle_battle import CycleMatchContribution
from app.models.campaign import CampaignSeason
from app.models.clan import ClanMember
from app.models.cycle_reinforcement_state import CycleReinforcementState
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_battle_service import CycleBattleService
from tests.test_cycle_arena_ingestion import saved
from tests.test_cycle_campaign_api import client_for
from tests.test_cycle_match_service import match_world
from tests.test_cycle_reinforcement_store import world, T


def finished(db):
    users, home, away, cycle, battle, replay = match_world(db)
    deadline = CampaignCycleStore.timeline(cycle).replay_deadline
    battle.completed_at = cycle.settled_at = deadline
    battle.winner_clan_id = battle.recalculated_winner_clan_id = home.id
    db.flush()
    return users, home, away, cycle, battle, replay


def late_matches(db, battle, **kwargs):
    from app.services.cycle_late_replay_service import CycleLateReplayService
    return CycleLateReplayService().read(db, battle_id=battle.id, **kwargs)


@pytest.mark.parametrize('database', ['db', 'postgres_db'])
def test_unrecorded_finished_battle_replay_is_found_by_frozen_uuid_without_writes(request, database):
    db = request.getfixturevalue(database)
    users, _, _, cycle, battle, replay = finished(db)
    users[2].display_name = 'Новое имя Арены'
    match = saved(db, replay)
    # Устаревшая локальная дата не скрывает поздно загруженный исходный ответ Арены.
    match.match_date = replay.started_at - timedelta(days=30)
    match.created_at = battle.completed_at + timedelta(minutes=1)
    db.flush()
    before = cycle.revision, battle.winner_clan_id, battle.recalculated_winner_clan_id
    statements = []
    listener = lambda _c, _s, statement, *_a: statements.append(statement)
    event.listen(db.bind, 'before_cursor_execute', listener)
    try:
        result = late_matches(db, battle)
    finally:
        event.remove(db.bind, 'before_cursor_execute', listener)
    assert len(result['items']) == 1
    item = result['items'][0]
    assert item['replay_id'] == 'bfmeladder:arena-1'
    assert item['source_replay_id'] == 'arena-1'
    assert {p['user_id'] for p in item['players']} == {users[2].id, users[3].id}
    assert next(p for p in item['players'] if p['user_id'] == users[2].id)['display_name'] == 'Новое имя Арены'
    assert item['historical_elo_available'] is False
    assert 'uuid' not in str(result) and 'source_payload' not in str(result)
    assert all(not sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for sql in statements)
    assert before == (cycle.revision, battle.winner_clan_id, battle.recalculated_winner_clan_id)
    assert db.query(CycleMatchContribution).count() == 0


@pytest.mark.parametrize('kind', ['foreign_uuid', 'before_battle', 'ends_after_battle', 'short', 'unranked', 'broken'])
def test_irrelevant_or_unverified_replays_are_not_presented_as_late_candidates(db, kind):
    _, _, _, cycle, battle, replay = finished(db)
    changes = {}
    if kind == 'foreign_uuid':
        replay = replace(replay, players=tuple(replace(p, uuid=str(UUID(int=900 + n)))
            for n, p in enumerate(replay.players)))
    elif kind == 'before_battle':
        replay = replace(replay, started_at=CampaignCycleStore.timeline(cycle).battle_at - timedelta(seconds=1))
    elif kind == 'ends_after_battle':
        replay = replace(replay, started_at=CampaignCycleStore.timeline(cycle).battle_ends_at - timedelta(minutes=5))
    elif kind == 'short':
        changes['duration'] = '00:00:59'
    elif kind == 'unranked':
        changes['players'] = [dict(uuid=p.uuid, team=p.team, isWinner=p.team == replay.winning_team)
            for p in replay.players]
    else:
        changes['replayId'] = 'чужой-ответ'
    saved(db, replay, raw_changes=changes)
    assert late_matches(db, battle)['items'] == []


def test_recorded_or_reviewed_player_is_not_proposed_again_but_missing_teammate_is_visible(db):
    users, home, _, _, battle, replay = finished(db)
    saved(db, replay)
    db.add(CycleMatchContribution(battle_id=battle.id, replay_id='bfmeladder:arena-1',
        user_id=users[2].id, clan_id=home.id, points=11, counted=False,
        reason='counted', review_reason='Решение администратора', reviewed_by_user_id=users[0].id))
    db.flush()
    item = late_matches(db, battle)['items'][0]
    assert [p['user_id'] for p in item['players']] == [users[3].id]


def test_pagination_advances_over_irrelevant_rows_without_losing_late_match(db):
    _, _, _, _, battle, replay = finished(db)
    for n in range(3):
        saved(db, replace(replay, replay_id=f'foreign-{n}', players=tuple(
            replace(p, uuid=str(UUID(int=900 + i))) for i, p in enumerate(replay.players))))
    match = saved(db, replay)
    first = late_matches(db, battle, limit=2)
    assert first['items'] == [] and first['next_after_id'] is not None
    second = late_matches(db, battle, after_id=first['next_after_id'], limit=2)
    assert [row['match_id'] for row in second['items']] == [match.id]
    assert second['next_after_id'] is None


def test_active_battle_and_missing_frozen_identities_fail_closed(db):
    _, _, _, cycle, battle, replay = match_world(db)
    saved(db, replay)
    with pytest.raises(ValueError):
        late_matches(db, battle)
    battle.completed_at = CampaignCycleStore.timeline(cycle).replay_deadline
    db.query(CycleReinforcementState).filter_by(cycle_id=cycle.id).delete()
    db.flush()
    with pytest.raises(ValueError):
        late_matches(db, battle)


def test_only_administrator_can_read_late_matches_and_public_battle_stays_unchanged(db):
    users, _, _, _, battle, replay = finished(db)
    saved(db, replay)
    url = f'/cycles/battles/{battle.id}/late-replays'
    ordinary = client_for(db, users[2])
    assert ordinary.get(url).status_code in (401, 403)
    admin = client_for(db, users[0], admin=True)
    response = admin.get(url)
    assert response.status_code == 200
    assert len(response.json()['items']) == 1
    assert 'late_replays' not in admin.get(f'/cycles/battles/{battle.id}').json()
    assert CycleBattleService().scores(db, battle.id) == {side['clan_id']: 0 for side in battle.sides}


def test_territory_detail_includes_current_display_name_not_only_internal_login(db):
    users, _, _, _, battle, _ = match_world(db)
    users[2].display_name = 'Новое имя Арены'
    db.flush()
    response = client_for(db, users[0], admin=True).get(f'/cycles/battles/{battle.id}')
    member = next(p for side in response.json()['sides'] for p in side['members'] if p['user_id'] == users[2].id)
    assert member['display_name'] == 'Новое имя Арены'


def test_fully_recorded_replay_does_not_return_and_administrative_exclusion_stays_intact(db):
    users, home, away, _, battle, replay = finished(db)
    saved(db, replay)
    for user, clan in ((users[2], home), (users[3], away)):
        db.add(CycleMatchContribution(battle_id=battle.id, replay_id='bfmeladder:arena-1',
            user_id=user.id, clan_id=clan.id, points=13, counted=False, reason='counted',
            review_reason='Отклонено администратором', reviewed_by_user_id=users[0].id))
    db.flush()
    assert late_matches(db, battle)['items'] == []
    assert late_matches(db, battle)['items'] == []
    assert all(not row.counted and row.points == 13 for row in db.query(CycleMatchContribution))


def test_member_who_left_before_the_match_remains_explicitly_ineligible(db):
    users, _, _, cycle, battle, replay = finished(db)
    db.query(ClanMember).filter_by(user_id=users[2].id).delete()
    saved(db, replay)
    item = late_matches(db, battle)['items'][0]
    assert next(p for p in item['players'] if p['user_id'] == users[2].id)['reason'] == 'membership_changed'
    db.get(CampaignSeason, cycle.season_id).rules_snapshot = {'mechanics_version': 'legacy'}
    db.flush()
    with pytest.raises(ValueError):
        late_matches(db, battle)


@pytest.mark.parametrize('parameters', [{'after_id': -1}, {'limit': 0}, {'limit': 501}, {'limit': True}])
def test_page_boundaries_are_validated(db, parameters):
    _, _, _, _, battle, _ = finished(db)
    with pytest.raises(ValueError):
        late_matches(db, battle, **parameters)


def test_interception_shows_new_display_name_without_changing_uuid_assignment(db, world):
    from tests.test_cycle_interception_service import setup, process
    from app.services.cycle_interception_service import CycleInterceptionService
    users = world[0]
    process(db, world, setup(db, world))
    users[1].display_name = 'Новое имя подкрепления'
    db.flush()
    result = CycleInterceptionService().read(db, cycle_id=world[3].id, dispatch_id='d', now=T + timedelta(hours=3))
    member = next(p for side in result['sides'] for p in side['members'] if p['user_id'] == users[1].id)
    assert member['display_name'] == 'Новое имя подкрепления'
