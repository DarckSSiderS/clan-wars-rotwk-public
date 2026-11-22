from decimal import Decimal

import pytest

from app.services.cycle_scoring import MatchPlayer, calculate_contributions, territory_winner


def player(identity, team, clan, elo=1500, *, side=None, bonus=0, exhausted=False):
    return MatchPlayer(identity=identity, team=team, clan_id=clan, elo=elo,
                       side_id=side, victory_bonus_percent=bonus, exhausted=exhausted)


def test_equal_elo_win_loss_and_personal_direct_multiplier():
    rows = [player('a', 1, 1, side=1), player('b', 2, 2, side=2)]
    result = calculate_contributions(rows, winning_team=1)
    assert result['a'].points == 200
    assert result['b'].points == -100
    assert result['a'].direct_multiplier == 2


@pytest.mark.parametrize('enemy,win,loss', [(1100, 50, -75), (1500, 100, -50), (1900, 150, -25), (2500, 150, -25)])
def test_elo_formula_clamp_without_direct_opponent(enemy, win, loss):
    rows = [player('a', 1, 1, side=1), player('b', 2, 2, elo=enemy)]
    assert calculate_contributions(rows, winning_team=1)['a'].points == win
    assert calculate_contributions(rows, winning_team=2)['a'].points == loss


def test_team_players_receive_full_personal_base_not_split():
    rows = [player('a', 1, 1, side=1), player('b', 1, 1, side=1),
            player('c', 2, 2), player('d', 2, 3)]
    result = calculate_contributions(rows, winning_team=1)
    assert result['a'].points == result['b'].points == 100


def test_direct_bonus_is_personal_and_not_activated_by_teammate():
    rows = [player('a', 1, 1, side=1), player('b', 1, 3, side=2),
            player('c', 2, 2, side=2), player('d', 2, 4)]
    result = calculate_contributions(rows, winning_team=1)
    assert result['a'].points == 200
    assert result['b'].points == 100


def test_ally_opponent_excludes_only_affected_personal_contribution():
    rows = [player('a', 1, 1, side=1), player('b', 1, 3, side=3), player('c', 2, 2, side=2)]
    result = calculate_contributions(rows, winning_team=1, alliances={(1, 2)})
    assert result['a'].points == 0
    assert result['a'].reason == 'allied_opponent'
    assert result['b'].points == 200
    assert result['c'].reason == 'allied_opponent'


def test_missing_elo_never_uses_1000_or_current_rating():
    rows = [player('a', 1, 1, side=1), player('b', 2, 2, elo=None)]
    result = calculate_contributions(rows, winning_team=1)
    assert result['a'].reason == 'missing_historical_elo'
    assert result['a'].points == 0


def test_bonus_is_capped_wins_only_and_exhaustion_applies_to_losses():
    rows = [player('a', 1, 1, side=1, bonus=80, exhausted=True), player('b', 2, 2, side=2)]
    assert calculate_contributions(rows, winning_team=1)['a'].points == 150
    assert calculate_contributions(rows, winning_team=2)['a'].points == -50


def test_draw_and_unknown_result_are_distinct():
    rows = [player('a', 1, 1, side=1), player('b', 2, 2, side=2)]
    assert calculate_contributions(rows, winning_team=None, draw=True)['a'].reason == 'draw'
    assert calculate_contributions(rows, winning_team=None)['a'].reason == 'unknown_result'


def test_fractional_scores_remain_exact():
    rows = [player('a', 1, 1, side=1), player('b', 2, 2, elo=1501)]
    assert calculate_contributions(rows, winning_team=1)['a'].points == Decimal('100.125')


def test_duplicate_identity_or_invalid_teams_cannot_be_scored():
    with pytest.raises(ValueError):
        calculate_contributions([player('a', 1, 1), player('a', 2, 2)], winning_team=1)
    with pytest.raises(ValueError):
        calculate_contributions([player('a', 1, 1)], winning_team=1)


@pytest.mark.parametrize('scores,owner,winner', [
    ({1: 10, 2: 20, 3: 15}, 1, 2),
    ({1: 20, 2: 20, 3: 15}, 3, 3),
    ({1: -5, 2: 0}, None, None),
    ({1: 1}, None, 1),
    ({1: 0}, None, None),
    ({}, 3, 3),
])
def test_multisided_territory_winner(scores, owner, winner):
    assert territory_winner(scores, owner_clan_id=owner) == winner
