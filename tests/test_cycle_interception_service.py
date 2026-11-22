from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.models.cycle_battle import CycleMatchContribution
from app.services.cycle_match_service import ReplayFacts, ReplayPlayer
from app.services.cycle_reinforcement_store import CycleReinforcementStore, decode_state
from tests.test_cycle_reinforcement_store import world, initialize, request, send, T


def service():
    from app.services.cycle_interception_service import CycleInterceptionService
    return CycleInterceptionService()


def setup(db, world, *, origin_territory_id=None):
    initialize(db, world)
    request(db, world)
    send(db, world, origin_territory_id=origin_territory_id)
    return ReplayFacts('interception-game', 'bfmeladder', 'ennorath', True,
        T + timedelta(hours=2), T + timedelta(hours=2, minutes=10),
        (ReplayPlayer(str(UUID(int=2)), 1, 1000, True, 'ennorath'),
         ReplayPlayer(str(UUID(int=7)), 2, 1000, True, 'ennorath')), 1)


def process(db, world, facts):
    return service().process(db, cycle_id=world[3].id, dispatch_id='d', replay=facts)


def verify(db, world):
    return service()._verify_window(db, cycle_id=world[3].id, dispatch_id='d',
        covered_start=T + timedelta(hours=2), covered_end=T + timedelta(hours=14),
        source_cursor='complete-source-cursor', now=T + timedelta(hours=14, minutes=5))


def finish(db, world, now=None):
    return service().finalize(db, cycle_id=world[3].id, dispatch_id='d',
        now=now or T + timedelta(hours=14, minutes=5))


def test_interception_scores_uuid_bound_once_and_never_territory_points(db, world):
    facts = setup(db, world)
    world[0][1].username = 'renamed helper'
    rows = process(db, world, facts)
    assert {r.user_id: r.points for r in rows} == {
        world[0][1].id: Decimal(200), world[0][6].id: Decimal(-100)}
    assert all(r.counted for r in rows)
    assert [r.id for r in process(db, world, facts)] == [r.id for r in rows]
    assert db.query(CycleMatchContribution).count() == 0
    verify(db, world)
    result = finish(db, world)
    assert result.outcome.value == 'exhausted'
    assert result.help_score == 200
    assert dict(result.ambush_scores) == {world[1][2].id: Decimal(-100)}
    assert result.arrives_at == T + timedelta(hours=24)
    assert world[3].dependencies['interception:d'] is True
    assert finish(db, world) == result


def test_interception_requires_verified_whole_window_and_grace(db, world):
    facts = setup(db, world)
    process(db, world, facts)
    with pytest.raises(ValueError, match='verified'):
        finish(db, world)
    with pytest.raises(ValueError):
        service()._verify_window(db, cycle_id=world[3].id, dispatch_id='d',
            covered_start=T + timedelta(hours=3), covered_end=T + timedelta(hours=14),
            source_cursor='incomplete', now=T + timedelta(hours=14, minutes=5))
    with pytest.raises(ValueError):
        service()._verify_window(db, cycle_id=world[3].id, dispatch_id='d',
            covered_start=T + timedelta(hours=2), covered_end=T + timedelta(hours=14),
            source_cursor='too-early', now=T + timedelta(hours=14, minutes=4, seconds=59))
    assert world[3].dependencies['interception:d'] is False


def test_verified_no_games_resolves_to_exhausted_not_blocked(db, world):
    setup(db, world)
    verify(db, world)
    result = finish(db, world)
    assert result.outcome.value == 'exhausted'
    assert result.help_score == 0
    assert dict(result.ambush_scores) == {world[1][2].id: Decimal(0)}


def test_pending_elo_blocks_resolution_until_enriched_and_reverified(db, world):
    facts = setup(db, world)
    missing = replace(facts, players=tuple(replace(p, historical=False) for p in facts.players))
    rows = process(db, world, missing)
    assert {r.reason for r in rows} == {'missing_historical_elo'}
    verify(db, world)
    with pytest.raises(ValueError, match='pending'):
        finish(db, world)
    rows = process(db, world, facts)
    assert all(r.counted for r in rows)
    with pytest.raises(ValueError, match='verified'):
        finish(db, world)
    verify(db, world)
    assert finish(db, world).outcome.value == 'exhausted'


@pytest.mark.parametrize('changes,reason', [
    ({'ranked': False}, 'not_ranked'),
    ({'patch_family': 'patch202'}, 'unsupported_patch'),
    ({'started_at': None}, 'missing_match_times'),
    ({'started_at': T + timedelta(hours=1, minutes=59)}, 'outside_battle_window'),
    ({'finished_at': T + timedelta(hours=14, seconds=1)}, 'outside_battle_window'),
    ({'finished_at': T + timedelta(hours=2, seconds=59)}, 'too_short'),
])
def test_interception_source_gates(db, world, changes, reason):
    facts = replace(setup(db, world), **changes)
    rows = process(db, world, facts)
    assert all(not r.counted and r.points == 0 and r.reason == reason for r in rows)


def test_new_game_after_verification_invalidates_coverage_and_late_change_needs_review(db, world):
    facts = setup(db, world)
    process(db, world, facts)
    verify(db, world)
    process(db, world, replace(facts, replay_id='second-game'))
    with pytest.raises(ValueError, match='verified'):
        finish(db, world)
    verify(db, world)
    result = finish(db, world)
    assert result.help_score == 400
    assert len(process(db, world, facts)) == 2
    with pytest.raises(ValueError, match='review'):
        process(db, world, replace(facts, replay_id='late-game'))
    with pytest.raises(ValueError, match='review'):
        process(db, world, replace(facts, winning_team=2))
    row = CycleReinforcementStore()._locked(db, world[3].id)[1]
    assert decode_state(row.payload['state']).dispatches[0].help_score == 400


def test_winning_ambush_blocks_help(db, world):
    facts = replace(setup(db, world), winning_team=2)
    process(db, world, facts)
    verify(db, world)
    result = finish(db, world)
    assert result.outcome.value == 'blocked'
    assert result.help_score == -100
    assert dict(result.ambush_scores)[world[1][2].id] == 200


@pytest.mark.parametrize('allied_bonus', [False, True])
def test_only_interception_relics_apply_from_own_frozen_snapshot(db, world, allied_bonus):
    from app.models.cycle_economy import CycleEconomyState, CycleEconomySnapshot
    facts = setup(db, world)
    wallet = CycleEconomyState(season_id=world[3].season_id, clan_id=world[1][0].id, wallet={})
    db.add(wallet)
    db.flush()
    db.add(CycleEconomySnapshot(cycle_id=world[3].id, state_id=wallet.id,
        effects=[{'key': 'palantir', 'level': 1, 'effect': 'interception_victory', 'percent': '20'},
                 *([{'key': 'red_arrow', 'level': 3, 'effect': 'allied_help_victory', 'percent': '40'}] if allied_bonus else []),
                 {'key': 'iron_crown', 'level': 3, 'effect': 'fortress_defense_victory', 'percent': '40'}],
        territory_upgrades={str(world[2].id): {'fortification': 3, 'offense': 3}},
        frozen_at=T, state_revision=1))
    db.flush()
    rows = process(db, world, facts)
    helper = next(r for r in rows if r.user_id == world[0][1].id)
    assert helper.points == (300 if allied_bonus else 240)
    assert helper.calculation['victory_bonus_percent'] == ('50' if allied_bonus else '20')
    assert helper.calculation['exhaustion_multiplier'] == '1'


def test_membership_end_is_exclusive_for_new_interception_games(db, world):
    from app.models.clan import ClanMembershipPeriod
    facts = setup(db, world)
    db.add(ClanMembershipPeriod(user_id=world[0][1].id, clan_id=world[1][0].id,
        started_at=T - timedelta(days=2), ended_at=facts.started_at))
    db.flush()
    rows = process(db, world, facts)
    helper = next(r for r in rows if r.user_id == world[0][1].id)
    assert not helper.counted and helper.reason == 'membership_changed'
    enemy = next(r for r in rows if r.user_id == world[0][6].id)
    assert enemy.points == -50  # Departed helper no longer creates direct x2.


def test_pending_elo_can_be_enriched_alongside_unchanged_membership_exclusion(db, world):
    from app.models.clan import ClanMembershipPeriod
    facts = setup(db, world)
    db.add(ClanMembershipPeriod(user_id=world[0][1].id, clan_id=world[1][0].id,
        started_at=T - timedelta(days=2), ended_at=facts.started_at))
    db.flush()
    missing = replace(facts, players=tuple(replace(p, historical=False) for p in facts.players))
    assert {r.reason for r in process(db, world, missing)} == {'membership_changed', 'missing_historical_elo'}
    rows = process(db, world, facts)
    assert {r.reason for r in rows} == {'membership_changed', 'counted'}
    verify(db, world)
    assert finish(db, world).outcome.value == 'exhausted'


def test_finalization_rolls_back_dependency_and_dispatch_together(db, world, monkeypatch):
    from app.models.cycle_interception import CycleInterception
    process(db, world, setup(db, world))
    verify(db, world)
    original = CycleReinforcementStore._resolve_interception
    def fail_after_resolution(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError('after resolution')
    with monkeypatch.context() as patch:
        patch.setattr(CycleReinforcementStore, '_resolve_interception', fail_after_resolution)
        with pytest.raises(RuntimeError):
            finish(db, world)
    assert db.query(CycleInterception).one().completed_at is None
    assert world[3].dependencies['interception:d'] is False
    assert CycleReinforcementStore()._locked(db, world[3].id)[2].dispatches[0].outcome.value == 'pending'
    assert finish(db, world).outcome.value == 'exhausted'


def fourth_ambush(db, world):
    from app.models.campaign_cycle import CampaignCyclePlan
    from app.models.clan import Clan, ClanMember
    from app.models.cycle_battle import CycleTerritoryBattle
    from app.models.external_identity import ExternalPlayerIdentity
    from app.models.user import User
    users, clans, land, cycle = world
    extra_user = User(username='fourth ordinary')
    db.add(extra_user)
    db.flush()
    extra = Clan(name='Fourth ambush clan', leader_id=users[7].id, level=1)
    db.add(extra)
    db.flush()
    db.add_all([ClanMember(user_id=u.id, clan_id=extra.id, joined_at=T - timedelta(days=20))
                for u in (users[7], extra_user)])
    db.add(ExternalPlayerIdentity(user_id=extra_user.id, source='bfmeladder', external_uuid=str(UUID(int=99)),
        current_nickname=extra_user.username, verification_status='verified'))
    db.add(CampaignCyclePlan(cycle_id=cycle.id, clan_id=extra.id, frozen_at=T,
        orders=[{'user_id': users[7].id, 'kind': 'ambush', 'territory_id': land.id},
                {'user_id': extra_user.id, 'kind': 'attack', 'territory_id': land.id}],
        snapshot={'level': 1, 'member_ids': [users[7].id, extra_user.id], 'allied_clan_ids': []}))
    battle = db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle.id).one()
    battle.sides = [*battle.sides, {'clan_id': extra.id, 'user_ids': [extra_user.id]}]
    db.flush()
    return extra


def test_two_ambushes_keep_independent_scores_and_cannot_farm_each_other(db, world):
    extra = fourth_ambush(db, world)
    clans = world[1]
    facts = setup(db, world)
    between = replace(facts, players=(replace(facts.players[0], uuid=str(UUID(int=7))),
                                     replace(facts.players[1], uuid=str(UUID(int=8)))))
    assert {r.reason for r in process(db, world, between)} == {'ambush_opponent'}
    outsider = ReplayPlayer(str(UUID(int=1000)), 2, 1000, True, 'ennorath')
    for identity in (2, 7, 8):
        process(db, world, replace(facts, replay_id=f'outside-{identity}',
            players=(ReplayPlayer(str(UUID(int=identity)), 1, 1000, True, 'ennorath'), outsider)))
    verify(db, world)
    result = finish(db, world)
    assert result.help_score == 100
    assert dict(result.ambush_scores) == {clans[2].id: Decimal(100), extra.id: Decimal(100)}
    assert result.outcome.value == 'exhausted'  # 100+100 is NOT compared with help 100.


def test_mixed_game_pending_helper_can_enrich_without_overwriting_ambush_exclusions(db, world):
    fourth_ambush(db, world)
    facts = setup(db, world)
    facts = replace(facts, players=(
        ReplayPlayer(str(UUID(int=2)), 1, 1000, True, 'ennorath'),
        ReplayPlayer(str(UUID(int=7)), 1, 1000, True, 'ennorath'),
        ReplayPlayer(str(UUID(int=8)), 2, 1000, True, 'ennorath'),
        ReplayPlayer(str(UUID(int=1000)), 2, 1000, True, 'ennorath')))
    missing = replace(facts, players=tuple(replace(p, historical=False) for p in facts.players))
    assert {r.reason for r in process(db, world, missing)} == {'ambush_opponent', 'missing_historical_elo'}
    rows = process(db, world, facts)
    assert len(rows) == 3
    assert sum(r.points for r in rows) == 200
    assert [r.reason for r in rows].count('ambush_opponent') == 2
    verify(db, world)
    assert finish(db, world).outcome.value == 'exhausted'


def test_runtime_really_settles_verified_interception_without_certifying_territory_scan(db, world):
    from app.services.cycle_runtime_service import CycleRuntimeService
    from app.services.cycle_startup_service import CycleStartupService
    cycle = world[3]
    cycle.number = 1
    db.flush()
    startup = CycleStartupService().initialize(db, cycle_id=cycle.id, now=T - timedelta(hours=96))
    startup.expired_at = T - timedelta(hours=24)
    db.flush()
    process(db, world, replace(setup(db, world), winning_team=2))
    verify(db, world)
    assert CycleRuntimeService().tick(db, now=T + timedelta(hours=14, minutes=5)) is True
    result = CycleReinforcementStore()._locked(db, cycle.id)[2].dispatches[0]
    assert result.outcome.value == 'blocked'
    assert cycle.dependencies['interception:d'] is True
    assert cycle.import_verified_at is None and cycle.settled_at is None


def test_interception_projection_is_read_only_and_excludes_source_identity(db, world):
    from app.models.cycle_interception import CycleInterception
    facts = setup(db, world)
    revision = world[3].revision
    with pytest.raises(ValueError):
        service().read(db, cycle_id=world[3].id, dispatch_id='d', now=T + timedelta(hours=1))
    result = service().read(db, cycle_id=world[3].id, dispatch_id='d', now=T + timedelta(hours=2))
    assert result['phase'] == 'battle'
    assert len(result['sides']) == 2
    assert world[3].revision == revision
    assert db.query(CycleInterception).count() == 0
    process(db, world, facts)
    result = service().read(db, cycle_id=world[3].id, dispatch_id='d', now=T + timedelta(hours=3))
    assert len(result['contributions']) == 2
    text = str(result)
    assert all(key not in text for key in ('input_fingerprint', 'source_cursor', '"uuid"', "'uuid'"))
    assert {r['score'] for r in result['sides']} == {'200.000000000000', '-100.000000000000'}


def test_interception_personal_summary_separates_wins_losses_and_net(db, world):
    facts = setup(db, world)
    process(db, world, facts)
    process(db, world, replace(facts, replay_id='lost-game', winning_team=2))
    result = service().read(db, cycle_id=world[3].id, dispatch_id='d', now=T + timedelta(hours=3))
    helper = next(m for side in result['sides'] for m in side['members'] if m['user_id'] == world[0][1].id)
    assert Decimal(helper['positive_points']) == 200
    assert Decimal(helper['negative_points']) == -100
    assert Decimal(helper['total_points']) == 100
