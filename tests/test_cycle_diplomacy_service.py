from datetime import datetime, timedelta, timezone

import pytest

from app.models.campaign import CampaignSeason
from app.models.clan import Clan
from app.models.user import User
from app.models.cycle_diplomacy import CycleDiplomacyEvent, CycleDiplomacyPair
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.campaign_cycle_service import CyclePhase
from app.services.cycle_diplomacy_service import CycleDiplomacyService, first_full_cycle


START = datetime(2026, 10, 15, tzinfo=timezone.utc)


@pytest.fixture
def world(db):
    users = [User(id=i, username=f'head{i}', email=f'h{i}@test.local', hashed_password='x') for i in (1, 2, 3)]
    db.add_all(users)
    db.flush()
    db.add_all([Clan(id=i, name=f'Clan{i}', leader_id=i) for i in (1, 2)])
    season = CampaignSeason(number=1, name='Diplomacy', status='active', starts_at=START,
                            rules_snapshot={'version': 1, 'mechanics_version': 'cycle_v1'})
    db.add(season)
    db.flush()
    cycle = CampaignCycleStore().start(db, season_id=season.id)
    return CycleDiplomacyService(), cycle, START + timedelta(hours=72)


def act(db, world, action, **kw):
    service, cycle, now = world
    args = dict(cycle_id=cycle.id, clan_id=1, other_clan_id=2, actor_user_id=1, now=now)
    args.update(kw)
    return getattr(service, action)(db, **args)


def view(db, world, now=None):
    service, cycle, prep = world
    return service.public_projection(db, season_id=cycle.season_id, now=now or prep)


def settle(db, cycle):
    store = CampaignCycleStore()
    end = store.timeline(cycle).replay_deadline
    cycle.orders_frozen_at = store.timeline(cycle).battle_at
    cycle.battles_registered = True
    db.flush()
    store.mark_import_complete(db, cycle_id=cycle.id, verified_at=end)
    store.settle(db, cycle_id=cycle.id, completed_at=end)
    return end


def test_directional_terms_and_settlement(db, world):
    act(db, world, 'declare_war', duration=1)
    act(db, world, 'declare_war', clan_id=2, other_clan_id=1, actor_user_id=2, duration=3)
    pair = view(db, world)[0]
    assert pair['status'] == 'hostile'
    assert pair['declarations']['1']['remaining_cycles'] == 1
    assert pair['declarations']['2']['remaining_cycles'] == 3
    end = settle(db, world[1])
    pair = view(db, world, end)[0]
    assert pair['status'] == 'hostile'
    assert set(pair['declarations']) == {'2'}
    assert pair['declarations']['2']['remaining_cycles'] == 2
    assert db.query(CycleDiplomacyPair).count() == 1
    assert db.query(CycleDiplomacyEvent).count() == 2


@pytest.mark.parametrize('duration', [0, -1, True, 1.5, '2', ''])
def test_invalid_duration_has_no_writes(db, world, duration):
    with pytest.raises(ValueError):
        act(db, world, 'declare_war', duration=duration)
    assert db.query(CycleDiplomacyPair).count() == 0
    assert db.query(CycleDiplomacyEvent).count() == 0


def test_no_arbitrary_duration_ceiling(db, world):
    act(db, world, 'declare_war', duration=10**80)
    assert view(db, world)[0]['declarations']['1']['remaining_cycles'] == 10**80


def test_head_only_and_phase_guard(db, world):
    for actor in (2, 3, True):
        with pytest.raises((ValueError, PermissionError)):
            act(db, world, 'declare_war', actor_user_id=actor, duration=1)
    for hours in (0, 96, 144):
        with pytest.raises(ValueError):
            act(db, world, 'declare_war', duration=1, now=START + timedelta(hours=hours))
    assert db.query(CycleDiplomacyPair).count() == 0


def test_mutual_peace_then_alliance_and_unilateral_break(db, world):
    act(db, world, 'declare_war', duration=None)
    with pytest.raises(ValueError):
        act(db, world, 'offer', kind='alliance')
    proposal = act(db, world, 'offer', kind='peace')
    assert 'proposals' not in view(db, world)[0]
    with pytest.raises(ValueError):
        act(db, world, 'accept', proposal_id=proposal.id)
    act(db, world, 'accept', proposal_id=proposal.id, clan_id=2, other_clan_id=1, actor_user_id=2)
    assert view(db, world)[0]['status'] == 'neutral'
    proposal = act(db, world, 'offer', kind='alliance')
    act(db, world, 'accept', proposal_id=proposal.id, clan_id=2, other_clan_id=1, actor_user_id=2)
    assert view(db, world)[0]['status'] == 'allied'
    with pytest.raises(ValueError):
        act(db, world, 'declare_war', duration=1)
    act(db, world, 'break_alliance')
    assert view(db, world)[0]['status'] == 'neutral'


def test_alliance_accept_rechecks_hostility_and_revocation(db, world):
    proposal = act(db, world, 'offer', kind='alliance')
    act(db, world, 'declare_war', duration=1)
    with pytest.raises(ValueError):
        act(db, world, 'accept', proposal_id=proposal.id, clan_id=2, other_clan_id=1, actor_user_id=2)
    act(db, world, 'revoke', proposal_id=proposal.id)
    assert world[0].proposal_status(db, proposal, cycle=world[1], now=world[2]) == 'revoked'
    with pytest.raises(ValueError):
        act(db, world, 'revoke', proposal_id=proposal.id)


def test_proposal_expires_only_after_two_full_settlements(db, world):
    proposal = act(db, world, 'offer', kind='alliance')
    service, cycle, _ = world
    assert proposal.expires_after_cycle == 2
    end = settle(db, cycle)
    assert service.proposal_status(db, proposal, cycle=cycle, now=end) == 'pending'
    next_cycle = CampaignCycleStore().advance(db, cycle_id=cycle.id, now=end + timedelta(hours=12), rule_version=1)
    end2 = settle(db, next_cycle)
    assert service.proposal_status(db, proposal, cycle=next_cycle, now=end2) == 'expired'
    with pytest.raises(ValueError):
        act(db, (service, next_cycle, end2), 'accept', proposal_id=proposal.id,
            clan_id=2, other_clan_id=1, actor_user_id=2)


@pytest.mark.parametrize('phase,expected', [(CyclePhase.PREPARATION, 5), (CyclePhase.REST, 6),
    (CyclePhase.BATTLE, 6), (CyclePhase.SETTLEMENT, 6), (CyclePhase.REPLAY_LOADING, 6)])
def test_explicit_full_cycle_selection(phase, expected):
    assert first_full_cycle(5, phase) == expected


def test_automatic_reveal_does_not_shorten_manual_war(db, world):
    service, cycle, prep = world
    act(db, world, 'declare_war', duration=20)
    battle = CampaignCycleStore.timeline(cycle).battle_at
    for _ in range(2):
        service.record_revealed_attack(db, cycle_id=cycle.id, attacker_clan_id=1, defender_clan_id=2, now=battle)
    assert view(db, world, battle)[0]['declarations']['1']['remaining_cycles'] == 20
    assert db.query(CycleDiplomacyEvent).count() == 3


def test_automatic_war_is_one_cycle_and_internal_phase_checked(db, world):
    service, cycle, prep = world
    with pytest.raises(ValueError):
        service.record_revealed_attack(db, cycle_id=cycle.id, attacker_clan_id=1, defender_clan_id=2, now=prep)
    battle = CampaignCycleStore.timeline(cycle).battle_at
    service.record_revealed_attack(db, cycle_id=cycle.id, attacker_clan_id=1, defender_clan_id=2, now=battle)
    assert view(db, world, battle)[0]['status'] == 'hostile'
    end = settle(db, cycle)
    assert view(db, world, end)[0]['status'] == 'neutral'


def test_caller_rollback_and_optimistic_revision(db, world):
    db.commit()
    act(db, world, 'declare_war', duration=1, expected_revision=0)
    with pytest.raises(CycleConflict):
        act(db, world, 'declare_war', duration=2, expected_revision=0)
    db.rollback()
    assert db.query(CycleDiplomacyPair).count() == 0
    assert db.query(CycleDiplomacyEvent).count() == 0


def test_season_isolation_opt_in_and_stale_cycle(db, world):
    act(db, world, 'declare_war', duration=None)
    end = settle(db, world[1])
    CampaignCycleStore().advance(db, cycle_id=world[1].id, now=end + timedelta(hours=12), rule_version=1)
    with pytest.raises(ValueError):
        act(db, world, 'declare_war', duration=1)
    db.get(CampaignSeason, world[1].season_id).status = 'ended'
    db.flush()
    other = CampaignSeason(number=2, name='Next', status='active', starts_at=START,
                           rules_snapshot={'version': 1, 'mechanics_version': 'cycle_v1'})
    db.add(other)
    db.flush()
    cycle = CampaignCycleStore().start(db, season_id=other.id)
    assert view(db, (world[0], cycle, world[2])) == []
    other.rules_snapshot = {'mechanics_version': 'legacy'}
    with pytest.raises(ValueError):
        act(db, (world[0], cycle, world[2]), 'declare_war', duration=1)


def test_public_projection_does_not_disclose_offer_existence_or_revision(db, world):
    act(db, world, 'offer', kind='alliance')
    assert view(db, world) == []
    act(db, world, 'declare_war', duration=3)
    before = view(db, world)
    proposal = act(db, world, 'offer', kind='peace')
    assert view(db, world) == before
    act(db, world, 'revoke', proposal_id=proposal.id)
    assert view(db, world) == before


def test_repeat_manual_war_replaces_only_own_term(db, world):
    act(db, world, 'declare_war', duration=5)
    act(db, world, 'declare_war', duration=None, clan_id=2, other_clan_id=1, actor_user_id=2)
    act(db, world, 'declare_war', duration=1)
    assert view(db, world)[0]['declarations']['1']['remaining_cycles'] == 1
    assert view(db, world)[0]['declarations']['2']['remaining_cycles'] is None
    assert db.query(CycleDiplomacyEvent).count() == 3


def test_rest_uses_next_cycle_and_current_head_from_database(db, world):
    end = settle(db, world[1])
    db.get(Clan, 1).leader_id = 3
    db.flush()
    with pytest.raises(PermissionError):
        act(db, world, 'declare_war', duration=1, now=end)
    act(db, world, 'declare_war', duration=1, now=end, actor_user_id=3)
    assert view(db, world, end)[0]['declarations']['1']['first_cycle'] == 2
    proposal = act(db, world, 'offer', kind='peace', now=end, actor_user_id=3)
    assert proposal.first_full_cycle == 2
    assert proposal.expires_after_cycle == 3


@pytest.mark.parametrize('overrides', [dict(clan_id=True), dict(other_clan_id='2'),
    dict(other_clan_id=1), dict(other_clan_id=999), dict(actor_user_id=None),
    dict(expected_revision=True), dict(now=START.replace(tzinfo=None))])
def test_strict_inputs_do_not_mutate(db, world, overrides):
    with pytest.raises((ValueError, PermissionError)):
        act(db, world, 'declare_war', duration=1, **overrides)
    assert db.query(CycleDiplomacyPair).count() == 0


def test_indefinite_attack_preserved(db, world):
    act(db, world, 'declare_war', duration=None)
    battle = CampaignCycleStore.timeline(world[1]).battle_at
    world[0].record_revealed_attack(db, cycle_id=world[1].id, attacker_clan_id=1, defender_clan_id=2, now=battle)
    assert view(db, world, battle)[0]['declarations']['1']['remaining_cycles'] is None


def test_allied_attack_rejected_without_audit_or_revision_change(db, world):
    proposal = act(db, world, 'offer', kind='alliance')
    pair = act(db, world, 'accept', proposal_id=proposal.id, clan_id=2, other_clan_id=1, actor_user_id=2)
    revision = pair.revision
    count = db.query(CycleDiplomacyEvent).count()
    with pytest.raises(ValueError):
        world[0].record_revealed_attack(db, cycle_id=world[1].id, attacker_clan_id=1,
            defender_clan_id=2, now=CampaignCycleStore.timeline(world[1]).battle_at)
    assert pair.revision == revision
    assert db.query(CycleDiplomacyEvent).count() == count


def test_reveal_recovery_after_gameplay_before_settlement(db, world):
    cycle = world[1]
    now = CampaignCycleStore.timeline(cycle).replay_deadline + timedelta(hours=1)
    world[0].record_revealed_attack(db, cycle_id=cycle.id, attacker_clan_id=1, defender_clan_id=2, now=now)
    assert view(db, world, now)[0]['declarations']['1']['remaining_cycles'] == 1


def test_target_cannot_revoke_or_accept_twice(db, world):
    proposal = act(db, world, 'offer', kind='alliance')
    args = dict(proposal_id=proposal.id, clan_id=2, other_clan_id=1, actor_user_id=2)
    with pytest.raises(ValueError):
        act(db, world, 'revoke', **args)
    act(db, world, 'accept', **args)
    with pytest.raises(ValueError):
        act(db, world, 'accept', **args)


def test_deleted_clan_and_unknown_proposal_rejected(db, world):
    with pytest.raises(ValueError):
        act(db, world, 'accept', proposal_id=999)
    db.get(Clan, 2).is_deleted = True
    db.flush()
    with pytest.raises(ValueError):
        act(db, world, 'declare_war', duration=1)
    assert db.query(CycleDiplomacyEvent).count() == 0
