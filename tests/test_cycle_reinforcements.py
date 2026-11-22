from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from app.services import cycle_reinforcements as r


T = datetime(2026, 10, 15, tzinfo=timezone.utc)


def player(n):
    return r.PlayerIdentity('arena', UUID(int=n))


def state(*, number=5, history=(), level=3, ambushes=()):
    return r.CycleReinforcements(
        number, T,
        (r.Reserve(1, level, (player(1), player(2), player(3))[:level]),
         r.Reserve(2, 1, (player(4),))),
        (r.Battle(10, (2, 3, 4)), r.Battle(11, (1, 3))),
        frozenset({frozenset({1, 2})}), tuple(history), tuple(ambushes),
    )


def send(s, *, at=T, request='q', players=(player(1),), dispatch='d'):
    s = s.request_help(request, 2, 10, T)
    return s.dispatch(dispatch, 1, players, 2, 10, at, request_id=request,
                      eligible_players=frozenset(players))


def test_selection_starts_cooldown_even_without_dispatch_and_across_clans():
    s = state()
    assert s.reserve_history == tuple(r.ReserveUse(p, 5) for p in
                                      (player(1), player(2), player(3), player(4)))
    for cycle in (6, 7):
        with pytest.raises(ValueError):
            state(number=cycle, history=s.reserve_history)
    assert state(number=8, history=s.reserve_history).number == 8
    with pytest.raises(ValueError):
        r.CycleReinforcements(6, T, (r.Reserve(9, 1, (player(1),)),), (),
                              frozenset(), s.reserve_history)


def test_frozen_capacity_and_no_mutation():
    s = state()
    with pytest.raises(FrozenInstanceError):
        s.reserves = ()
    # Dispatch takes no live level: all three frozen slots survive III -> II.
    s = send(s, players=(player(1), player(2), player(3)))
    assert len(s.dispatches[0].players) == 3
    assert replace(s) == s


@pytest.mark.parametrize('offset,allowed', [(-1, False), (0, True),
                                           (86399, True), (86400, False)])
def test_dispatch_window(offset, allowed):
    if allowed:
        assert send(state(), at=T + timedelta(seconds=offset)).dispatches
    else:
        with pytest.raises(ValueError):
            send(state(), at=T + timedelta(seconds=offset))


def test_delivery_and_no_redirect_or_resend_and_replays():
    s = send(state())
    assert send(s) == s
    assert s.request_help('q', 2, 10, T) == s
    with pytest.raises(ValueError):
        s.dispatch('d', 1, (player(1),), 1, 11, T,
                   eligible_players=frozenset({player(1)}))
    with pytest.raises(ValueError):
        send(s, request='q2', dispatch='d2')
    assert s.territory_factor('d', T + timedelta(hours=24) - timedelta(microseconds=1)) == 0
    assert s.territory_factor('d', T + timedelta(hours=24)) == 1
    assert s.territory_factor('d', T + timedelta(hours=48)) == 0
    assert s.dispatches[0].recipient_clan_id == 2
    assert s.dispatches[0].sender_clan_id == 1


def test_request_first_success_and_failed_send_does_not_consume():
    s = state().request_help('q', 2, 10, T)
    with pytest.raises(ValueError):
        s.dispatch('d', 1, (player(1),), 2, 10, T, request_id='q',
                   eligible_players=frozenset())
    assert s.requests[0].dispatch_id is None
    s = send(s)
    with pytest.raises(ValueError):
        send(s, players=(player(2),), dispatch='other')
    assert send(s, request='new', players=(player(2),), dispatch='other').requests[-1].dispatch_id == 'other'


def test_help_diplomacy_and_own_side_checks():
    with pytest.raises(ValueError):
        send(replace(state(), alliances=frozenset()))
    with pytest.raises(ValueError):
        send(replace(state(), alliances=frozenset({frozenset({1, 2}), frozenset({1, 3})})))
    with pytest.raises(ValueError):
        send(replace(state(), battles=(r.Battle(10, (1, 2, 3)),)))


def ambush(clan=3, n=30, territory=10):
    return r.Ambush(clan, territory, (player(n),))


def test_ambush_visibility_first_eligible_group_and_replay():
    s = state(ambushes=(ambush(),))
    assert s.visible_ambushes(1) == ()
    assert s.visible_ambushes(3) == s.ambushes
    s = send(s)
    assert len(s.visible_ambushes(1)) == 1
    assert s.ambushes[0].dispatch_id == 'd'
    assert send(s) == s
    later = send(s, request='q2', dispatch='d2', players=(player(2),))
    assert later.ambushes == s.ambushes
    assert later.dispatches[1].ambush_clan_ids == ()


def test_ineligible_group_does_not_reveal_or_consume_ambush():
    s = replace(state(ambushes=(ambush(),)),
                alliances=frozenset({frozenset({1, 2}), frozenset({1, 3})}))
    # Own reinforcement to clan 2 avoids the allied-help conflict for sender 1.
    s = s.dispatch('own', 2, (player(4),), 2, 10, T,
                   eligible_players=frozenset({player(4)}))
    assert s.ambushes[0].dispatch_id == 'own'
    allied = replace(state(ambushes=(ambush(),)),
                     alliances=frozenset({frozenset({1, 2}), frozenset({2, 3})}))
    allied = send(allied)
    assert allied.visible_ambushes(1) == ()
    assert allied.ambushes[0].dispatch_id is None


@pytest.mark.parametrize('scores,help_score,blocked', [
    ((10, 11), 10, True), ((6, 6), 10, False), ((10, 10), 10, False),
    ((0, -1), -2, False), ((1, 1), -2, True), ((0, 0), 0, False),
])
def test_independent_ambush_scores(scores, help_score, blocked):
    s = send(state(ambushes=(ambush(), ambush(4, 40))))
    d = s.dispatches[0]
    assert d.interception_at == T + timedelta(hours=2)
    assert d.interception_ends_at == T + timedelta(hours=14)
    assert d.arrives_at == T + timedelta(hours=24)
    result_at = d.interception_ends_at + timedelta(minutes=5)
    with pytest.raises(ValueError):
        s.resolve('d', help_score, {3: scores[0], 4: scores[1]}, result_at - timedelta(microseconds=1))
    result = s.resolve('d', help_score, {3: scores[0], 4: scores[1]}, result_at)
    assert result.dispatches[0].outcome == (r.Outcome.BLOCKED if blocked else r.Outcome.EXHAUSTED)
    assert result.territory_factor('d', d.arrives_at) == (0 if blocked else Decimal('0.5'))
    assert result.resolve('d', help_score, {3: scores[0], 4: scores[1]}, result_at) == result
    with pytest.raises(ValueError):
        result.resolve('d', help_score + 1, {3: scores[0], 4: scores[1]}, result_at)


def test_interception_window_and_unresolved_no_territory_credit():
    s = send(state(ambushes=(ambush(),)))
    start, end = T + timedelta(hours=2), T + timedelta(hours=14)
    assert s.interception_match_allowed('d', start, end - timedelta(microseconds=1))
    assert not s.interception_match_allowed('d', start - timedelta(microseconds=1), start)
    assert s.interception_match_allowed('d', start, end)
    assert not s.interception_match_allowed('d', start, end + timedelta(microseconds=1))
    assert not s.interception_match_allowed('d', end, start)
    assert s.territory_factor('d', T + timedelta(hours=24)) == 0
    with pytest.raises(ValueError):
        s.resolve('d', 0, {}, end + timedelta(minutes=5))
    with pytest.raises(ValueError):
        s.resolve('d', float('nan'), {3: 1}, end + timedelta(minutes=5))


@pytest.mark.parametrize('bad', [
    lambda: r.PlayerIdentity('', UUID(int=1)),
    lambda: r.PlayerIdentity('arena', 'nickname'),
    lambda: r.Reserve(1, 1, (player(1), player(2))),
    lambda: r.Reserve(1, 2, (player(1), player(1))),
    lambda: r.Ambush(3, 10, ()),
    lambda: r.Ambush(3, 10, (player(1), player(2), player(3))),
    lambda: state(ambushes=(ambush(), ambush(3, 31))),
    lambda: state(ambushes=(ambush(n=1),)),
    lambda: state(ambushes=(ambush(9),)),
    lambda: replace(state(), battle_at=T.replace(tzinfo=None)),
])
def test_validation(bad):
    with pytest.raises(ValueError):
        bad()


def test_delayed_dispatch_and_exhaustion_never_extend_travel_or_compound():
    sent = T + timedelta(hours=12)
    s = send(state(ambushes=(ambush(), ambush(4, 40))), at=sent)
    d = s.dispatches[0]
    assert d.arrives_at == T + timedelta(hours=36)
    s = s.resolve('d', 10, {3: 9, 4: 9}, sent + timedelta(hours=14, minutes=5))
    assert s.territory_factor('d', d.arrives_at) == Decimal('0.5')
    assert Decimal('-15') * s.territory_factor('d', d.arrives_at) == Decimal('-7.5')
    assert s.territory_factor('d', d.arrives_at - timedelta(microseconds=1)) == 0


def test_source_uuid_identity_and_defensive_collection_freezing():
    assert player(1) != r.PlayerIdentity('other', player(1).uuid)
    original = [player(1)]
    reserve = r.Reserve(1, 1, original)
    original.clear()
    assert reserve.players == (player(1),)
    assert state().reserve_history[0].player == player(1)


def test_ordinary_assignments_cannot_overlap_reserve_or_ambush():
    for n in (1, 30):
        with pytest.raises(ValueError):
            replace(state(ambushes=(ambush(),)), battles=(r.Battle(10, (2, 3), (player(n),)),))


def test_different_target_stays_hidden_and_does_not_block_delivery():
    s = send(state(ambushes=(ambush(3, territory=11),)))
    assert s.visible_ambushes() == ()
    assert s.dispatches[0].outcome == r.Outcome.CLEAR
    assert s.territory_factor('d', T + timedelta(hours=24)) == 1
    with pytest.raises(ValueError):
        s.resolve('d', 0, {}, T + timedelta(hours=25))


def test_conflicting_request_replay_and_open_request_duplication():
    s = state().request_help('q', 2, 10, T)
    with pytest.raises(ValueError):
        s.request_help('q', 3, 10, T)
    with pytest.raises(ValueError):
        s.request_help('another', 2, 10, T)


@pytest.mark.parametrize('change', [
    lambda s: replace(s, ambushes=(replace(s.ambushes[0], dispatch_id=None),)),
    lambda s: replace(s, requests=(replace(s.requests[0], dispatch_id=None),)),
    lambda s: replace(s, dispatches=(replace(s.dispatches[0], players=(player(99),)),)),
    lambda s: replace(s, reserve_history=s.reserve_history + (r.ReserveUse(player(99), 6),)),
    lambda s: replace(s, reserves=(r.Reserve(1, 1, (player(1),)),)),
])
def test_invalid_restored_state_rejected(change):
    with pytest.raises(ValueError):
        change(send(state(ambushes=(ambush(),))))


def test_finished_dispatch_replay_does_not_recheck_live_membership():
    s = send(state(ambushes=(ambush(),)))
    s = s.resolve('d', 10, {3: 0}, T + timedelta(hours=14, minutes=5))
    assert s.dispatch('d', 1, (player(1),), 2, 10, T, request_id='q',
                      eligible_players=frozenset()) is s
