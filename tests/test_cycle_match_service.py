from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.models.cycle_battle import CycleMatchContribution
from app.models.clan import Clan, ClanMember
from app.models.cycle_diplomacy import CycleDiplomacyPair
from app.models.external_identity import ExternalPlayerIdentity
from app.models.user import User
from app.services.cycle_battle_service import CycleBattleService
from app.services.cycle_match_service import CycleMatchService, ReplayFacts, ReplayPlayer
from app.services.cycle_reveal_service import CycleRevealService
from tests.test_cycle_reveal_service import prepared
from tests.test_cycle_reinforcement_store import world, initialize, request, send, T
from app.services.cycle_reinforcement_store import CycleReinforcementStore


def match_world(db):
    users, home, away, _, cycle, now = prepared(db)
    battle = CycleRevealService().reveal(db, cycle_id=cycle.id, now=now)[0]
    facts = ReplayFacts(replay_id='arena-1', source='bfmeladder', patch_family='ennorath', ranked=True,
        started_at=now + timedelta(minutes=10), finished_at=now + timedelta(minutes=20),
        players=(ReplayPlayer(str(UUID(int=users[2].id)), 1, 1000, True, 'ennorath'),
                 ReplayPlayer(str(UUID(int=users[3].id)), 2, 1000, True, 'ennorath')),
        winning_team=2)
    return users, home, away, cycle, battle, facts


def test_direct_match_is_bound_to_uuid_not_display_name_and_imports_once(db):
    users, home, away, _, battle, facts = match_world(db)
    users[2].username = 'renamed after reveal'
    db.flush()
    service = CycleMatchService()
    rows = service.process(db, battle_id=battle.id, replay=facts)
    assert {row.clan_id: row.points for row in rows} == {home.id: Decimal(-100), away.id: Decimal(200)}
    assert all(row.counted and row.reason == 'counted' for row in rows)
    assert rows[1].calculation['direct_multiplier'] == 2
    service.process(db, battle_id=battle.id, replay=facts)
    assert db.query(CycleMatchContribution).count() == 2
    assert CycleBattleService().scores(db, battle.id) == {home.id: Decimal(-100), away.id: Decimal(200)}


def test_scout_cannot_score_even_if_present_in_a_stale_battle_snapshot(db):
    from app.models.campaign_cycle import CycleScoutRequest
    users, home, _, cycle, battle, facts = match_world(db)
    db.add(CycleScoutRequest(cycle_id=cycle.id, clan_id=home.id, territory_id=battle.territory_id,
        actor_user_id=users[0].id, scout_user_id=users[2].id, scout_uuid=str(UUID(int=users[2].id)),
        requested_at=facts.started_at))
    db.flush()
    rows = CycleMatchService().process(db, battle_id=battle.id, replay=facts)
    scout = next(row for row in rows if row.user_id == users[2].id)
    assert scout.points == 0 and not scout.counted and scout.reason == 'scouting'


@pytest.mark.parametrize(('changes', 'reason'), [
    ({'ranked': False}, 'not_ranked'),
    ({'patch_family': 'patch202'}, 'unsupported_patch'),
    ({'started_at': None}, 'missing_match_times'),
])
def test_source_gates_keep_a_visible_rejection_reason(db, changes, reason):
    _, _, _, _, battle, facts = match_world(db)
    rows = CycleMatchService().process(db, battle_id=battle.id, replay=replace(facts, **changes))
    assert all(not row.counted and row.reason == reason and row.points == 0 for row in rows)


@pytest.mark.parametrize(('seconds', 'counted'), [(59, False), (60, True)])
def test_minute_limit_uses_confirmed_start_and_finish(db, seconds, counted):
    _, _, _, _, battle, facts = match_world(db)
    facts = replace(facts, finished_at=facts.started_at + timedelta(seconds=seconds))
    rows = CycleMatchService().process(db, battle_id=battle.id, replay=facts)
    assert all(row.counted == counted for row in rows)
    if not counted:
        assert {row.reason for row in rows} == {'too_short'}


def test_current_profile_rating_is_never_treated_as_historical_and_can_be_enriched(db):
    _, _, _, _, battle, facts = match_world(db)
    unverified = replace(facts, players=tuple(replace(p, historical=False) for p in facts.players))
    service = CycleMatchService()
    rows = service.process(db, battle_id=battle.id, replay=unverified)
    assert all(row.reason == 'missing_historical_elo' and not row.counted for row in rows)
    rows = service.process(db, battle_id=battle.id, replay=facts)
    assert all(row.counted for row in rows)
    assert db.query(CycleMatchContribution).count() == 2


def test_rating_for_another_patch_does_not_substitute_the_requested_patch(db):
    _, _, _, _, battle, facts = match_world(db)
    rows = CycleMatchService().process(db, battle_id=battle.id,
        replay=replace(facts, players=tuple(replace(p, rating_patch='patch202') for p in facts.players)))
    assert all(row.reason == 'missing_historical_elo' for row in rows)


@pytest.mark.parametrize('new_clan', [False, True])
def test_wallet_created_after_reveal_cannot_block_or_buff_current_matches(db, new_clan):
    from app.models.cycle_economy import CycleEconomyState
    _, home, _, cycle, battle, facts = match_world(db)
    clan = home
    if new_clan:
        clan = Clan(name='Joined season after reveal')
        db.add(clan)
        db.flush()
    wallet = CycleEconomyState(season_id=cycle.season_id, clan_id=clan.id, wallet={},
        relics={'war_foundry': 3}, active_relics=['war_foundry'])
    db.add(wallet)
    db.flush()
    rows = CycleMatchService().process(db, battle_id=battle.id, replay=facts)
    assert all(r.counted for r in rows)
    assert {r.points for r in rows} == {Decimal(-100), Decimal(200)}


def test_missing_required_frozen_economy_snapshot_still_fails_closed(db):
    from app.models.cycle_economy import CycleEconomySnapshot
    from app.services.cycle_economy_store import CycleEconomyStore
    users, home, away, _, cycle, now = prepared(db)
    CycleEconomyStore().ensure_state(db, season_id=cycle.season_id, clan_id=home.id)
    battle = CycleRevealService().reveal(db, cycle_id=cycle.id, now=now)[0]
    db.query(CycleEconomySnapshot).filter_by(cycle_id=cycle.id).delete()
    db.flush()
    facts = ReplayFacts('missing-snapshot', 'bfmeladder', 'ennorath', True,
        now + timedelta(minutes=1), now + timedelta(minutes=2),
        (ReplayPlayer(str(UUID(int=users[2].id)), 1, 1000, True, 'ennorath'),
         ReplayPlayer(str(UUID(int=users[3].id)), 2, 1000, True, 'ennorath')), 1)
    with pytest.raises(ValueError, match='snapshot'):
        CycleMatchService().process(db, battle_id=battle.id, replay=facts)


def test_import_does_not_override_explicit_admin_rejection(db):
    users, _, _, _, battle, facts = match_world(db)
    service = CycleMatchService()
    rows = service.process(db, battle_id=battle.id, replay=facts)
    row = rows[0]
    CycleBattleService().review_contribution(db, battle_id=battle.id, replay_id=row.replay_id,
        user_id=row.user_id, counted=False, actor_user_id=users[0].id, reason='Reviewed manually')
    service.process(db, battle_id=battle.id, replay=facts)
    db.refresh(row)
    assert row.counted is False and row.review_reason == 'Reviewed manually'


def test_duplicate_or_invalid_permanent_identity_rejected_without_partial_scores(db):
    _, _, _, _, battle, facts = match_world(db)
    with pytest.raises(ValueError, match='identity'):
        CycleMatchService().process(db, battle_id=battle.id,
            replay=replace(facts, players=(facts.players[0], replace(facts.players[1], uuid=facts.players[0].uuid))))
    assert db.query(CycleMatchContribution).count() == 0


def test_pending_interception_defers_both_sides_then_applies_exhausted_ally_points(db, world):
    users, clans, land, cycle = world
    initialize(db, world)
    request(db, world)
    send(db, world)
    from app.models.cycle_battle import CycleTerritoryBattle
    battle = db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle.id, territory_id=land.id).one()
    facts = ReplayFacts(replay_id='help-match', source='bfmeladder', patch_family='ennorath', ranked=True,
        started_at=T + timedelta(hours=24), finished_at=T + timedelta(hours=24, minutes=10),
        players=(ReplayPlayer(str(UUID(int=2)), 1, 1000, True, 'ennorath'),
                 ReplayPlayer(str(UUID(int=6)), 2, 1000, True, 'ennorath')), winning_team=1)
    service = CycleMatchService()
    pending = service.process(db, battle_id=battle.id, replay=facts)
    assert all(row.reason == 'interception_pending' and not row.counted for row in pending)
    CycleReinforcementStore()._resolve_interception(db, cycle_id=cycle.id, dispatch_id='d',
        help_score=100, ambush_scores={clans[2].id: 0}, now=T + timedelta(hours=14, minutes=5))
    rows = service.process(db, battle_id=battle.id, replay=facts)
    helper = next(row for row in rows if row.user_id == users[1].id)
    opponent = next(row for row in rows if row.user_id == users[5].id)
    assert helper.clan_id == clans[1].id and helper.points == Decimal(100)
    assert helper.calculation['actual_clan_id'] == clans[0].id
    assert helper.calculation['exhaustion_multiplier'] == '0.5'
    assert opponent.points == Decimal(-100)


def test_unassigned_allied_opponent_uses_frozen_roster_and_diplomacy(db):
    users, home, _, _, cycle, now = prepared(db)
    ally_user = User(username='No orders ally')
    db.add(ally_user)
    db.flush()
    ally = Clan(name='No orders allies', level=1, leader_id=ally_user.id)
    db.add(ally)
    db.flush()
    db.add_all([ClanMember(user_id=ally_user.id, clan_id=ally.id, joined_at=now - timedelta(days=1)),
        ExternalPlayerIdentity(user_id=ally_user.id, source='bfmeladder', external_uuid=str(UUID(int=42)),
            current_nickname=ally_user.username, verification_status='verified')])
    relation = CycleDiplomacyPair(season_id=cycle.season_id, clan_low_id=min(home.id, ally.id),
        clan_high_id=max(home.id, ally.id), allied_at=now - timedelta(hours=1), declarations={})
    db.add(relation)
    db.flush()
    battle = CycleRevealService().reveal(db, cycle_id=cycle.id, now=now)[0]
    relation.allied_at = None
    ally_user.username = 'Later rename'
    db.flush()
    facts = ReplayFacts(replay_id='ally-game', source='bfmeladder', patch_family='ennorath', ranked=True,
        started_at=now + timedelta(minutes=10), finished_at=now + timedelta(minutes=20),
        players=(ReplayPlayer(str(UUID(int=users[2].id)), 1, 1000, True, 'ennorath'),
                 ReplayPlayer(str(UUID(int=42)), 2, 1000, True, 'ennorath')), winning_team=1)
    rows = CycleMatchService().process(db, battle_id=battle.id, replay=facts)
    assert len(rows) == 1 and rows[0].user_id == users[2].id
    assert rows[0].reason == 'allied_opponent' and not rows[0].counted
