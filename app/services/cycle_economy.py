"""Pure new-season economy rules; no persistence or application dependencies.

Based on the five balance/decision documents dated October 11-15, 2026.
Prices are per transition, not cumulative. Callers own authorization, durable
gift eligibility, transactions, reservations, routes and cycle lifecycle.
No territory IDs or unresolved category ranges are assigned here. Fee rounding
is unapproved: quotes retain Decimal fractions without quantization.
"""

from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Mapping, Iterable


def _amount(value) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, str, Decimal)):
        raise TypeError('Use Decimal, integer or decimal string, never float')
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('Invalid decimal amount') from exc
    if not number.is_finite() or number < 0:
        raise ValueError('Amounts must be finite and nonnegative')
    return number


@dataclass(frozen=True)
class Resources:
    gold: Decimal = Decimal(0)
    iron: Decimal = Decimal(0)
    wood: Decimal = Decimal(0)
    food: Decimal = Decimal(0)
    mithril: Decimal = Decimal(0)

    def __post_init__(self):
        for field in fields(self):
            object.__setattr__(self, field.name, _amount(getattr(self, field.name)))

    def __add__(self, other: 'Resources') -> 'Resources':
        if not isinstance(other, Resources):
            return NotImplemented
        return Resources(**{key: getattr(self, key) + getattr(other, key) for key in RESOURCE_NAMES})


RESOURCE_NAMES = tuple(field.name for field in fields(Resources))
MATERIALS = RESOURCE_NAMES[1:]
START_RESOURCES = Resources(1000, 30, 30, 20, 5)
BASE_DAILY_INCOME = Resources(100, 2, 2, 2)
RELIC_LOADOUT_SIZE = 4
MARKET_BUY = MappingProxyType(dict(zip(MATERIALS, map(Decimal, (45, 40, 30, 300)))))
MARKET_SELL = MappingProxyType(dict(zip(MATERIALS, map(Decimal, (10, 8, 6, 60)))))


class InsufficientFunds(ValueError):
    """A pure operation could not pay its entire cost."""


def debit(balance: Resources, cost: Resources) -> Resources:
    amounts = {key: getattr(balance, key) - getattr(cost, key) for key in RESOURCE_NAMES}
    if any(value < 0 for value in amounts.values()):
        raise InsufficientFunds('All resources must be available before purchase')
    return Resources(**amounts)


def system_market(balance: Resources, resource: str, quantity, *, buying: bool) -> Resources:
    """No construction discounts apply to either side of the system market."""
    if resource not in MATERIALS:
        raise ValueError('Only materials can be bought or sold')
    quantity = _amount(quantity)
    if not quantity:
        raise ValueError('Quantity must be positive')
    if not isinstance(buying, bool):
        raise TypeError('buying must be boolean')
    cargo = Resources(**{resource: quantity})
    if buying:
        return debit(balance, Resources(gold=MARKET_BUY[resource] * quantity)) + cargo
    return debit(balance, cargo) + Resources(gold=MARKET_SELL[resource] * quantity)


def barter_fee(received: Resources) -> Decimal:
    if received.gold or not any(getattr(received, key) for key in MATERIALS):
        raise ValueError('Barter requires a nonempty material-only cargo')
    return sum((getattr(received, key) * MARKET_BUY[key] for key in MATERIALS), Decimal(0)) * Decimal('0.1')


@dataclass(frozen=True)
class BarterAcceptance:
    first_balance: Resources
    second_balance: Resources
    first_fee: Decimal
    second_fee: Decimal
    to_first: Resources
    to_second: Resources


def accept_barter(first: Resources, second: Resources, offered: Resources, requested: Resources,
                  *, first_at_war=False, second_at_war=False, first_has_land=True,
                  second_has_land=True, route_available=True) -> BarterAcceptance:
    """Quote both debits and in-transit cargo, never credit delivery immediately.

    Call with currently spendable balances (excluding other reservations) and
    restore this offer's own reserved cargo before evaluation. Eligibility must
    also be checked at offer creation. Persist both debits/cargo atomically;
    this function performs no persistence and does not determine travel time.
    """
    if first_at_war or second_at_war or not (first_has_land and second_has_land and route_available):
        raise ValueError('Current diplomacy, land and route must allow barter')
    first_fee, second_fee = barter_fee(requested), barter_fee(offered)
    first_after = debit(first, offered + Resources(gold=first_fee))
    second_after = debit(second, requested + Resources(gold=second_fee))
    return BarterAcceptance(first_after, second_after, first_fee, second_fee, requested, offered)


@dataclass(frozen=True)
class Upgrade:
    costs: tuple[Resources, ...]
    effects: tuple[Decimal, ...]


def _upgrade(costs, effects):
    return Upgrade(tuple(Resources(*row) for row in costs), tuple(_amount(v) for v in effects))


# Economic effects are cumulative additions; military effects replace levels.
UPGRADES = MappingProxyType({
    'gold': _upgrade(((300,5,10,5,0),(1000,15,25,15,0),(2500,30,50,30,3)), (35,115,265)),
    'profile': _upgrade(((200,5,10,5,0),(600,15,20,10,0),(1500,30,40,25,2)), (2,5,10)),
    'mithril': _upgrade(((400,10,10,10,1),(1200,25,20,20,3),(3000,50,40,35,6)), ('0.5','1.25','2.5')),
    'fortification': _upgrade(((500,15,10,5,0),(1500,35,25,10,2),(3500,70,50,20,5)), (5,10,20)),
    'offense': _upgrade(((500,15,5,15,0),(1500,35,15,35,2),(3500,70,30,70,5)), (5,10,20)),
    'naval': _upgrade(((600,10,25,10,0),(1800,25,60,25,2),(4000,50,120,50,5)), (5,10,20)),
})


def _level(level, *, minimum=0, maximum=3):
    if type(level) is not int or not minimum <= level <= maximum:
        raise ValueError(f'Level must be an integer from {minimum} to {maximum}')
    return level


def upgrade_effect(branch: str, level: int) -> Decimal:
    _level(level)
    if branch not in UPGRADES:
        raise ValueError('Unknown upgrade branch')
    return UPGRADES[branch].effects[level - 1] if level else Decimal(0)


def upgrade_cost(branch: str, current_level: int, snapshot=()) -> Resources:
    """Cost of the next immediate level, with only applicable snapshot discounts."""
    _level(current_level, maximum=2)
    if branch not in UPGRADES:
        raise ValueError('Unknown upgrade branch')
    cost = UPGRADES[branch].costs[current_level]
    values = {key: getattr(cost, key) for key in RESOURCE_NAMES}
    if branch in ('gold', 'profile', 'mithril'):
        values['gold'] *= 1 - _effect(snapshot, 'economic_gold_discount') / 100
    elif branch == 'fortification':
        multiplier = 1 - _effect(snapshot, 'fortification_material_discount') / 100
        for key in ('iron', 'wood'):
            values[key] *= multiplier
    return Resources(**values)


@dataclass(frozen=True)
class Relic:
    name: str
    effect: str
    effects: tuple[Decimal, ...]
    costs: tuple[Resources, ...]


def _relic(name, effect, effects, costs):
    return Relic(name, effect, tuple(_amount(v) for v in effects), tuple(Resources(*row) for row in costs))


# Existing stable keys, including mordor_forge for the renamed food relic.
RELICS = MappingProxyType({
    'royal_charter': _relic('Королевская грамота', 'influence', (15,25,35),
        ((2500,10,25,15,3),(5000,20,50,30,6),(10000,40,100,60,12))),
    'war_foundry': _relic('Клановая кузница', 'territorial_victory', (10,15,20),
        ((3000,30,15,15,4),(6000,60,30,30,8),(12000,120,60,60,16))),
    'mithril_standard': _relic('Мифриловый штандарт', 'attack_victory', (15,25,35),
        ((3500,30,15,20,6),(7000,60,30,40,12),(14000,120,60,80,24))),
    'granite_bastion': _relic('Гранитный бастион', 'defense_victory', (15,25,35),
        ((3500,35,25,10,6),(7000,70,50,20,12),(14000,140,100,40,24))),
    'merchant_guild': _relic('Гильдия торговцев', 'economic_gold_discount', (10,20,30),
        ((3000,10,30,20,4),(300,5,10,5,1),(700,10,15,10,2))),
    'white_tree': _relic('Знамя Белого Древа', 'gold', (15,25,35),
        ((3000,15,25,20,4),(1000,10,15,10,2),(1800,20,25,20,3))),
    'red_arrow': _relic('Красная стрела Рохана', 'allied_help_victory', (20,30,40),
        ((2500,15,25,25,3),(5000,30,50,50,6),(10000,60,100,100,12))),
    'iron_crown': _relic('Железная корона', 'fortress_defense_victory', (20,30,40),
        ((3000,35,15,15,4),(6000,70,30,30,8),(12000,140,60,60,16))),
    'palantir': _relic('Палантир Ортханка', 'interception_victory', (20,30,40),
        ((3500,15,20,25,6),(7000,30,40,50,12),(14000,60,80,100,24))),
    'dwarf_anvil': _relic('Наковальня Глубин', 'iron', (20,35,50),
        ((3000,30,15,15,4),(900,15,10,10,2),(1600,25,20,15,3))),
    'ents_seed': _relic('Семя Энтов', 'wood', (20,35,50),
        ((3000,10,35,20,4),(800,10,15,10,2),(1400,20,25,15,3))),
    'mordor_forge': _relic('Житницы Нурна', 'food', (20,35,50),
        ((3000,25,20,30,4),(600,10,10,15,2),(1100,20,20,25,3))),
    'helms_horn': _relic('Рог Хельмовой Пади', 'direct_defense_victory', (20,30,40),
        ((3000,25,25,20,4),(6000,50,50,40,8),(12000,100,100,80,16))),
    'ring_of_barahir': _relic('Кольцо Барахира', 'fortification_material_discount', (10,20,30),
        ((3500,25,20,20,6),(7000,50,40,40,12),(14000,100,80,80,24))),
    'galadhrim_mirror': _relic('Зеркало Галадриэли', 'mithril', (15,25,35),
        ((4000,15,30,25,8),(700,10,15,10,2),(1400,20,25,20,3))),
})


def _collection(owned):
    for key, level in owned.items():
        if key not in RELICS:
            raise ValueError('Unknown relic')
        _level(level, minimum=1)


def starting_relics(selected: Iterable[str]) -> dict[str, int]:
    """Caller must enforce durable once-only eligibility, including recreation."""
    selected = tuple(selected)
    if len(selected) != 2 or len(set(selected)) != 2 or any(key not in RELICS for key in selected):
        raise ValueError('Choose exactly two distinct catalog relics')
    return dict.fromkeys(selected, 1)


def buy_relic(balance: Resources, owned: Mapping[str, int], key: str) -> tuple[Resources, dict[str, int]]:
    """Buy the next level without influence gates; leave the collection intact."""
    _collection(owned)
    if key not in RELICS:
        raise ValueError('Unknown relic')
    current = owned.get(key, 0)
    _level(current, maximum=2)
    remaining = debit(balance, RELICS[key].costs[current])
    return remaining, {**owned, key: current + 1}


@dataclass(frozen=True)
class RelicEffect:
    key: str
    level: int
    effect: str
    percent: Decimal


def relic_snapshot(owned: Mapping[str, int], selected: Iterable[str]) -> tuple[RelicEffect, ...]:
    """Copy selected levels/effects at reveal, or evaluate the live rest loadout."""
    _collection(owned)
    selected = tuple(selected)
    if len(selected) > RELIC_LOADOUT_SIZE or len(set(selected)) != len(selected):
        raise ValueError('At most four distinct active relics')
    if any(key not in owned for key in selected):
        raise ValueError('Only owned relics may be active')
    return tuple(RelicEffect(key, owned[key], RELICS[key].effect,
                            RELICS[key].effects[owned[key] - 1]) for key in selected)


def select_relics(owned: Mapping[str, int], selected: Iterable[str], *, phase: str) -> tuple[str, ...]:
    if phase not in ('rest', 'preparation'):
        raise ValueError('The active set is frozen during a cycle')
    return tuple(row.key for row in relic_snapshot(owned, selected))


def _effect(snapshot, effect: str) -> Decimal:
    # One catalog item per economic effect: no unapproved cross-effect stacking.
    return sum((row.percent for row in snapshot if row.effect == effect), Decimal(0))


def territory_income(base: Resources, profile: str | None, *, gold_level=0,
                     profile_level=0, snapshot=()) -> Resources:
    """Explicit verified map income only; no category inference or port stacking.

    Returned daily income excludes the unconditional clan base. Economic land
    levels apply immediately; relic percentages come from the cycle snapshot.
    """
    _level(profile_level)
    if profile is not None and profile not in MATERIALS:
        raise ValueError('Unknown fixed resource profile')
    if any(getattr(base, key) for key in MATERIALS if key != profile):
        raise ValueError('Base must contain only its fixed profile material')
    if profile_level and (profile is None or not getattr(base, profile)):
        raise ValueError('An upgrade cannot create a new resource profile')
    values = {key: getattr(base, key) for key in RESOURCE_NAMES}
    values['gold'] += upgrade_effect('gold', gold_level)
    if profile is not None:
        branch = 'mithril' if profile == 'mithril' else 'profile'
        values[profile] += upgrade_effect(branch, profile_level)
    for key in RESOURCE_NAMES:
        values[key] *= 1 + _effect(snapshot, key) / 100
    return Resources(**values)


def victory_bonus(snapshot=(), *, role: str, won=True, allied_help=False,
                  direct=False, fortress=False, naval=False, fortification_level=0,
                  offense_level=0, naval_level=0) -> Decimal:
    """Personal victory percent for scoring, capped before direct/exhaustion.

    Supply military levels from the reveal snapshot for the defended territory
    or the assigned source land/port. These are not current mutable map levels.
    Allied helpers use their own clan's relic snapshot.
    """
    if role not in ('attack', 'defense', 'interception'):
        raise ValueError('Unknown battle role')
    for level in (fortification_level, offense_level, naval_level):
        _level(level)
    if not won:
        return Decimal(0)
    effects = {'allied_help_victory'} if allied_help else set()
    bonus = Decimal(0)
    if role == 'interception':
        effects.add('interception_victory')
    else:
        effects.add('territorial_victory')
        if role == 'attack':
            effects.add('attack_victory')
            bonus += upgrade_effect('naval', naval_level) if naval else upgrade_effect('offense', offense_level)
        else:
            effects.add('defense_victory')
            bonus += upgrade_effect('fortification', fortification_level)
            if fortress:
                bonus += 10
                effects.add('fortress_defense_victory')
            if direct:
                effects.add('direct_defense_victory')
    bonus += sum((row.percent for row in snapshot if row.effect in effects), Decimal(0))
    return min(Decimal(50), bonus)
