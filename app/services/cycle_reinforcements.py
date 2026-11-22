"""Pure new-season reserve/help rules. No persistence, clock, or live lookups.

The caller supplies frozen ordinary battle sides and alliances, authorized
commands, and currently dispatch-eligible reserve identities (membership and
exit rules). Persist the returned aggregate atomically with optimistic locking;
pure transitions alone cannot arbitrate concurrent writes. Times use [start,
end) windows. Reserve history must follow identities across clan changes.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from uuid import UUID


def _positive(value):
    if type(value) is not int or value < 1:
        raise ValueError('Positive integer required')


def _key(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Nonempty stable command ID required')


def _time(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Timezone-aware datetime required')
    return value.astimezone(timezone.utc)


def _players(values, *, minimum=0, maximum=None):
    result = tuple(values)
    if (any(not isinstance(p, PlayerIdentity) for p in result)
            or len(set(result)) != len(result) or len(result) < minimum
            or (maximum is not None and len(result) > maximum)):
        raise ValueError('Unique permanent player identities required within capacity')
    return result


def _score(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('Finite score required') from None
    if not result.is_finite():
        raise ValueError('Finite score required')
    return result


@dataclass(frozen=True)
class PlayerIdentity:
    source: str
    uuid: UUID

    def __post_init__(self):
        _key(self.source)
        if not isinstance(self.uuid, UUID) or self.uuid.int == 0:
            raise ValueError('Source UUID required, never a nickname')


@dataclass(frozen=True)
class ReserveUse:
    player: PlayerIdentity
    cycle: int

    def __post_init__(self):
        _players((self.player,))
        _positive(self.cycle)


@dataclass(frozen=True)
class Reserve:
    clan_id: int
    capacity: int
    players: tuple[PlayerIdentity, ...]

    def __post_init__(self):
        _positive(self.clan_id)
        _positive(self.capacity)
        object.__setattr__(self, 'players', _players(self.players, maximum=self.capacity))


@dataclass(frozen=True)
class Battle:
    territory_id: int
    clan_ids: tuple[int, ...]
    ordinary_players: tuple[PlayerIdentity, ...] = ()

    def __post_init__(self):
        _positive(self.territory_id)
        sides = tuple(self.clan_ids)
        for clan in sides:
            _positive(clan)
        if not sides or len(set(sides)) != len(sides):
            raise ValueError('Unique battle sides required')
        object.__setattr__(self, 'clan_ids', sides)
        object.__setattr__(self, 'ordinary_players', _players(self.ordinary_players))


@dataclass(frozen=True)
class Ambush:
    clan_id: int
    territory_id: int
    players: tuple[PlayerIdentity, ...]
    dispatch_id: str | None = None

    def __post_init__(self):
        _positive(self.clan_id)
        _positive(self.territory_id)
        object.__setattr__(self, 'players', _players(self.players, minimum=1, maximum=2))
        if self.dispatch_id is not None:
            _key(self.dispatch_id)


@dataclass(frozen=True)
class HelpRequest:
    id: str
    recipient_clan_id: int
    territory_id: int
    requested_at: datetime
    dispatch_id: str | None = None

    def __post_init__(self):
        _key(self.id)
        _positive(self.recipient_clan_id)
        _positive(self.territory_id)
        object.__setattr__(self, 'requested_at', _time(self.requested_at))
        if self.dispatch_id is not None:
            _key(self.dispatch_id)


class Outcome(str, Enum):
    CLEAR = 'clear'
    PENDING = 'pending'
    BLOCKED = 'blocked'
    EXHAUSTED = 'exhausted'


@dataclass(frozen=True)
class Dispatch:
    id: str
    sender_clan_id: int
    players: tuple[PlayerIdentity, ...]
    recipient_clan_id: int
    territory_id: int
    sent_at: datetime
    request_id: str | None
    ambush_clan_ids: tuple[int, ...] = ()
    outcome: Outcome = Outcome.CLEAR
    help_score: Decimal | None = None
    ambush_scores: tuple[tuple[int, Decimal], ...] = ()

    def __post_init__(self):
        _key(self.id)
        for value in (self.sender_clan_id, self.recipient_clan_id, self.territory_id):
            _positive(value)
        object.__setattr__(self, 'players', _players(self.players, minimum=1))
        object.__setattr__(self, 'sent_at', _time(self.sent_at))
        if self.request_id is not None:
            _key(self.request_id)
        clans = tuple(self.ambush_clan_ids)
        for clan in clans:
            _positive(clan)
        if len(set(clans)) != len(clans):
            raise ValueError('Duplicate ambush side')
        object.__setattr__(self, 'ambush_clan_ids', clans)
        if not isinstance(self.outcome, Outcome):
            raise ValueError('Explicit outcome required')
        scores = tuple(sorted((clan, _score(score)) for clan, score in self.ambush_scores))
        object.__setattr__(self, 'ambush_scores', scores)
        if self.help_score is not None:
            object.__setattr__(self, 'help_score', _score(self.help_score))
        if self.outcome in (Outcome.CLEAR, Outcome.PENDING):
            if (bool(clans) != (self.outcome == Outcome.PENDING)
                    or self.help_score is not None or scores):
                raise ValueError('Invalid unresolved dispatch')
        else:
            if (not clans or self.help_score is None
                    or tuple(c for c, _ in scores) != tuple(sorted(clans))):
                raise ValueError('Complete independent scores required')
            blocked = any(score > 0 and score > self.help_score for _, score in scores)
            if blocked != (self.outcome == Outcome.BLOCKED):
                raise ValueError('Outcome disagrees with scores')

    @property
    def arrives_at(self):
        return self.sent_at + timedelta(hours=24)

    @property
    def interception_at(self):
        return self.sent_at + timedelta(hours=2) if self.ambush_clan_ids else None

    @property
    def interception_ends_at(self):
        return self.sent_at + timedelta(hours=14) if self.ambush_clan_ids else None


@dataclass(frozen=True)
class CycleReinforcements:
    number: int
    battle_at: datetime
    reserves: tuple[Reserve, ...]
    battles: tuple[Battle, ...]
    alliances: frozenset[frozenset[int]] = frozenset()
    reserve_history: tuple[ReserveUse, ...] = ()
    ambushes: tuple[Ambush, ...] = ()
    requests: tuple[HelpRequest, ...] = ()
    dispatches: tuple[Dispatch, ...] = ()

    def __post_init__(self):
        _positive(self.number)
        object.__setattr__(self, 'battle_at', _time(self.battle_at))
        for name in ('reserves', 'battles', 'reserve_history', 'ambushes', 'requests', 'dispatches'):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        alliances = frozenset(frozenset(pair) for pair in self.alliances)
        for pair in alliances:
            if len(pair) != 2:
                raise ValueError('Alliance requires two different clans')
            for clan in pair:
                _positive(clan)
        object.__setattr__(self, 'alliances', alliances)
        for items, key in ((self.reserves, 'clan_id'), (self.battles, 'territory_id'),
                           (self.ambushes, 'clan_id'), (self.requests, 'id'), (self.dispatches, 'id')):
            if len({getattr(item, key) for item in items}) != len(items):
                raise ValueError('Duplicate frozen assignment or command ID')
        all_players = [p for item in (*self.reserves, *self.ambushes) for p in item.players]
        all_players += [p for b in self.battles for p in b.ordinary_players]
        _players(all_players)
        history = tuple(self.reserve_history)
        if len(set(history)) != len(history) or any(h.cycle > self.number for h in history):
            raise ValueError('Invalid reserve history')
        chosen = {p for reserve in self.reserves for p in reserve.players}
        if any(h.player in chosen and self.number - 2 <= h.cycle < self.number for h in history):
            raise ValueError('Reserve blocked until cycle N+3')
        if any(h.cycle == self.number and h.player not in chosen for h in history):
            raise ValueError('Frozen reserve cannot be removed midcycle')
        additions = tuple(ReserveUse(p, self.number) for reserve in self.reserves
                          for p in reserve.players if ReserveUse(p, self.number) not in history)
        object.__setattr__(self, 'reserve_history', history + additions)
        for ambush in self.ambushes:
            if ambush.clan_id not in self._battle(ambush.territory_id).clan_ids:
                raise ValueError('Ambush requires own ordinary battle side')
        used = []
        for dispatch in self.dispatches:
            self._validate_route(dispatch.sender_clan_id, dispatch.recipient_clan_id,
                                 dispatch.territory_id, dispatch.request_id)
            if not self.battle_at <= dispatch.sent_at < self.battle_at + timedelta(hours=24):
                raise ValueError('Dispatch outside first 24 hours')
            reserve = next((r for r in self.reserves if r.clan_id == dispatch.sender_clan_id), None)
            if reserve is None or not set(dispatch.players) <= set(reserve.players):
                raise ValueError('Dispatch must use own frozen reserve')
            used.extend(dispatch.players)
            triggered = tuple(a.clan_id for a in self.ambushes if a.dispatch_id == dispatch.id)
            if set(triggered) != set(dispatch.ambush_clan_ids):
                raise ValueError('Ambush links disagree')
            for a in self.ambushes:
                if a.dispatch_id == dispatch.id and not self._can_intercept(a, dispatch):
                    raise ValueError('Ineligible ambush')
            if dispatch.request_id is not None:
                request = next((q for q in self.requests if q.id == dispatch.request_id), None)
                if (request is None or request.dispatch_id != dispatch.id
                        or request.recipient_clan_id != dispatch.recipient_clan_id
                        or request.territory_id != dispatch.territory_id
                        or request.requested_at > dispatch.sent_at):
                    raise ValueError('Invalid request linkage')
        _players(used)
        for a in self.ambushes:
            if a.dispatch_id is not None:
                self._dispatch(a.dispatch_id)
        for q in self.requests:
            if q.recipient_clan_id not in self._battle(q.territory_id).clan_ids:
                raise ValueError('Recipient must have a battle side')
            if not self.battle_at <= q.requested_at < self.battle_at + timedelta(hours=48):
                raise ValueError('Request outside battle')
            if q.dispatch_id is not None and self._dispatch(q.dispatch_id).request_id != q.id:
                raise ValueError('Request closure disagrees with dispatch')

    def _battle(self, territory_id):
        battle = next((b for b in self.battles if b.territory_id == territory_id), None)
        if battle is None:
            raise ValueError('Unknown battle territory')
        return battle

    def _dispatch(self, dispatch_id):
        dispatch = next((d for d in self.dispatches if d.id == dispatch_id), None)
        if dispatch is None:
            raise ValueError('Unknown dispatch')
        return dispatch

    def _allied(self, first, second):
        return frozenset((first, second)) in self.alliances

    def _validate_route(self, sender, recipient, territory, request_id):
        sides = self._battle(territory).clan_ids
        if recipient not in sides:
            raise ValueError('Recipient must have a battle side')
        if sender != recipient:
            if (request_id is None or sender in sides or not self._allied(sender, recipient)
                    or any(self._allied(sender, c) for c in sides if c != recipient)):
                raise ValueError('Allied help conflicts with frozen diplomacy or own side')
        elif request_id is not None:
            raise ValueError('Own reinforcements do not close allied requests')

    def _can_intercept(self, ambush, dispatch):
        return (ambush.territory_id == dispatch.territory_id
                and ambush.clan_id != dispatch.recipient_clan_id
                and ambush.clan_id != dispatch.sender_clan_id
                and not self._allied(ambush.clan_id, dispatch.sender_clan_id)
                and not self._allied(ambush.clan_id, dispatch.recipient_clan_id))

    def request_help(self, request_id, recipient_clan_id, territory_id, at):
        request = HelpRequest(request_id, recipient_clan_id, territory_id, at)
        old = next((q for q in self.requests if q.id == request_id), None)
        if old is not None:
            if replace(old, dispatch_id=None) != request:
                raise ValueError('Conflicting request replay')
            return self
        if any(q.recipient_clan_id == recipient_clan_id and q.territory_id == territory_id
               and q.dispatch_id is None for q in self.requests):
            raise ValueError('An open request already exists')
        return replace(self, requests=self.requests + (request,))

    def dispatch(self, dispatch_id, sender_clan_id, players, recipient_clan_id,
                 territory_id, at, *, eligible_players, request_id=None):
        players = _players(players, minimum=1)
        at = _time(at)
        old = next((d for d in self.dispatches if d.id == dispatch_id), None)
        command = (sender_clan_id, players, recipient_clan_id, territory_id, at, request_id)
        if old is not None:
            if command != (old.sender_clan_id, old.players, old.recipient_clan_id,
                           old.territory_id, old.sent_at, old.request_id):
                raise ValueError('Cannot redirect or change dispatch replay')
            return self
        if not set(players) <= set(_players(eligible_players)):
            raise ValueError('Players no longer eligible for dispatch')
        self._validate_route(sender_clan_id, recipient_clan_id, territory_id, request_id)
        requests = self.requests
        if request_id is not None:
            request = next((q for q in requests if q.id == request_id), None)
            if request is None or request.dispatch_id is not None:
                raise ValueError('Request missing or already closed')
            requests = tuple(replace(q, dispatch_id=dispatch_id) if q.id == request_id else q
                             for q in requests)
        dispatch = Dispatch(dispatch_id, sender_clan_id, players, recipient_clan_id,
                            territory_id, at, request_id)
        matches = tuple(a.clan_id for a in self.ambushes
                        if a.dispatch_id is None and self._can_intercept(a, dispatch))
        if matches:
            dispatch = replace(dispatch, ambush_clan_ids=matches, outcome=Outcome.PENDING)
        ambushes = tuple(replace(a, dispatch_id=dispatch_id)
                         if a.clan_id in matches else a for a in self.ambushes)
        return replace(self, requests=requests, ambushes=ambushes,
                       dispatches=self.dispatches + (dispatch,))

    def visible_ambushes(self, viewer_clan_id=None):
        """Projection for non-admin viewers; untriggered orders stay private."""
        return tuple(a for a in self.ambushes
                     if a.clan_id == viewer_clan_id or a.dispatch_id is not None)

    def interception_match_allowed(self, dispatch_id, started_at, ended_at):
        d = self._dispatch(dispatch_id)
        start, end = _time(started_at), _time(ended_at)
        return bool(d.ambush_clan_ids and d.interception_at <= start < end <= d.interception_ends_at)

    def resolve(self, dispatch_id, help_score, ambush_scores, at):
        d = self._dispatch(dispatch_id)
        at = _time(at)
        if not d.ambush_clan_ids or at < d.interception_ends_at + timedelta(minutes=5):
            raise ValueError('Interception replay loading has not finished')
        help_score = _score(help_score)
        scores = tuple(sorted((clan, _score(score)) for clan, score in ambush_scores.items()))
        if tuple(c for c, _ in scores) != tuple(sorted(d.ambush_clan_ids)):
            raise ValueError('Exactly one independent score per ambush required')
        if d.outcome != Outcome.PENDING:
            if d.help_score != help_score or d.ambush_scores != scores:
                raise ValueError('Late corrections require separate administrative review')
            return self
        blocked = any(score > 0 and score > help_score for _, score in scores)
        resolved = replace(d, help_score=help_score, ambush_scores=scores,
                           outcome=Outcome.BLOCKED if blocked else Outcome.EXHAUSTED)
        return replace(self, dispatches=tuple(resolved if item.id == d.id else item
                                             for item in self.dispatches))

    def territory_factor(self, dispatch_id, match_started_at):
        """Only arrival/dispatch eligibility; caller still validates full match."""
        d = self._dispatch(dispatch_id)
        start = _time(match_started_at)
        if (not d.arrives_at <= start < self.battle_at + timedelta(hours=48)
                or d.outcome in (Outcome.PENDING, Outcome.BLOCKED)):
            return Decimal(0)
        return Decimal('0.5') if d.outcome == Outcome.EXHAUSTED else Decimal(1)
