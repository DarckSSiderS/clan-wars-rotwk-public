"""Personal scoring for one new-season battle, using its frozen assignments."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping


def _decimal(value):
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError('Finite numbers are required')
    return number


@dataclass(frozen=True)
class MatchPlayer:
    identity: str
    team: int
    clan_id: int | None
    elo: int | Decimal | None
    side_id: int | None = None
    victory_bonus_percent: int | Decimal = 0
    exhausted: bool = False


@dataclass(frozen=True)
class Contribution:
    points: Decimal
    reason: str
    base_points: Decimal = Decimal(0)
    victory_bonus_percent: Decimal = Decimal(0)
    direct_multiplier: int = 1
    exhaustion_multiplier: Decimal = Decimal(1)


def calculate_contributions(players, *, winning_team, draw=False, alliances=()):
    """All players require historical patch Elo; assignment side is battle-specific.

    Callers must first validate patch, ranked status, window, membership and
    assignment arrival. A missing side means this participant has no assignment
    in this battle, not a missing Arena participant.
    """
    players = tuple(players)
    if len({p.identity for p in players}) != len(players) or any(not p.identity for p in players):
        raise ValueError('Every player needs a unique permanent identity')
    teams = {p.team for p in players}
    if len(teams) != 2:
        raise ValueError('Exactly two complete teams are required')
    if winning_team is not None and winning_team not in teams:
        raise ValueError('Winner must be a participating team')
    if draw and winning_team is not None:
        raise ValueError('Draw cannot also have a winning team')
    allies = {frozenset(pair) for pair in alliances}
    ratings = {p.identity: None if p.elo is None else _decimal(p.elo) for p in players}
    if any(value is not None and value < 0 for value in ratings.values()):
        raise ValueError('Elo cannot be negative')
    bonuses = {p.identity: _decimal(p.victory_bonus_percent) for p in players}
    if any(value < 0 for value in bonuses.values()):
        raise ValueError('Victory bonuses cannot be negative')
    complete_elo = all(value is not None for value in ratings.values())
    averages = {}
    if complete_elo:
        for team in teams:
            values = [ratings[p.identity] for p in players if p.team == team]
            averages[team] = sum(values, Decimal(0)) / len(values)
    results = {}
    for player in players:
        opponents = [p for p in players if p.team != player.team]
        reason = None
        if player.side_id is None:
            reason = 'not_assigned'
        elif any(player.clan_id is not None and p.clan_id == player.clan_id for p in opponents):
            reason = 'clan_opponent'
        elif any(player.clan_id is not None and p.clan_id is not None
                 and frozenset((player.clan_id, p.clan_id)) in allies for p in opponents):
            reason = 'allied_opponent'
        elif draw:
            reason = 'draw'
        elif winning_team is None:
            reason = 'unknown_result'
        elif not complete_elo:
            reason = 'missing_historical_elo'
        if reason is not None:
            results[player.identity] = Contribution(Decimal(0), reason)
            continue
        enemy_team = opponents[0].team
        difference = max(Decimal(-400), min(Decimal(400), averages[enemy_team] - averages[player.team]))
        won = player.team == winning_team
        base = Decimal(100) + difference / 8 if won else Decimal(-50) + difference / 16
        bonus = min(Decimal(50), bonuses[player.identity]) if won else Decimal(0)
        direct = 2 if any(p.side_id is not None and p.side_id != player.side_id for p in opponents) else 1
        exhausted = Decimal('0.5') if player.exhausted else Decimal(1)
        points = base * (1 + bonus / 100) * direct * exhausted
        results[player.identity] = Contribution(points, 'counted', base, bonus, direct, exhausted)
    return results


def territory_winner(scores: Mapping[int, Decimal], *, owner_clan_id):
    if not scores:
        return owner_clan_id
    values = {key: _decimal(value) for key, value in scores.items()}
    maximum = max(values.values())
    leaders = [key for key, value in values.items() if value == maximum]
    return leaders[0] if maximum > 0 and len(leaders) == 1 else owner_clan_id
