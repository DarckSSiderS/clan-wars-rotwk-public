"""Validate hidden plans against a stable preparation snapshot, never names."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TerritoryState:
    id: int
    owner_clan_id: int | None
    neighbours: frozenset[int] = frozenset()
    coastal: bool = False
    port: bool = False
    fortress: bool = False


@dataclass(frozen=True)
class Order:
    user_id: int
    kind: str
    territory_id: int | None = None
    source_id: int | None = None
    route: str = 'land'


@dataclass(frozen=True)
class PlanningContext:
    clan_id: int
    level: int
    influence: int
    member_ids: frozenset[int]
    reserve_blocked_ids: frozenset[int]
    territories: tuple[TerritoryState, ...]
    allied_clan_ids: frozenset[int] = frozenset()
    scouting_ids: frozenset[int] = frozenset()


def attack_limit(land_count: int) -> int:
    if type(land_count) is not int or land_count < 0:
        raise ValueError('Nonnegative land count required')
    return 2 if land_count <= 2 else 3 if land_count <= 4 else 4 if land_count <= 6 else 5


def validate_plan(orders, context: PlanningContext) -> tuple[Order, ...]:
    orders = tuple(orders)
    if context.level < 1:
        raise ValueError('Positive clan level required')
    territories = {t.id: t for t in context.territories}
    if len(territories) != len(context.territories):
        raise ValueError('Duplicate territory snapshot')
    owned = {t.id for t in territories.values() if t.owner_clan_id == context.clan_id}
    seen = set()
    for order in orders:
        if order.user_id in seen:
            raise ValueError('duplicate assignment')
        seen.add(order.user_id)
        if order.user_id not in context.member_ids:
            raise ValueError('Player is not an eligible member')
        if order.user_id in context.scouting_ids:
            raise ValueError('Player is scouting until the end of this cycle')
        if order.kind not in {'attack', 'defend', 'reserve', 'ambush'}:
            raise ValueError('Unknown order kind')
        if order.route not in {'land', 'sea'}:
            raise ValueError('Unknown route')
        if order.kind == 'reserve':
            if order.territory_id is not None or order.source_id is not None or order.route != 'land':
                raise ValueError('Reserve has no destination yet')
            if order.user_id in context.reserve_blocked_ids:
                raise ValueError('Reserve cooldown has not ended')
            continue
        target = territories.get(order.territory_id)
        if target is None:
            raise ValueError('Unknown territory')
        if order.kind in {'defend', 'ambush'}:
            if order.source_id is not None or order.route != 'land':
                raise ValueError('Only attacks have a route source')
            if order.kind == 'defend' and target.id not in owned:
                raise ValueError('Defence requires owned land')
            continue
        if target.id in owned:
            raise ValueError('Cannot attack owned land')
        if target.owner_clan_id in context.allied_clan_ids:
            raise ValueError('Cannot attack an ally')
        if not owned:
            if target.port or target.fortress:
                raise ValueError('landless attacks exclude ports and fortresses')
            if order.source_id is not None or order.route != 'land':
                raise ValueError('landless attack has no owned source')
            continue
        if target.fortress and (len(owned) < 5 or context.influence < 350):
            raise ValueError('fortress requires five lands and 350 influence')
        source = territories.get(order.source_id)
        if source is None or source.id not in owned:
            raise ValueError('Attack source must be owned')
        if order.route == 'sea':
            if not source.port:
                raise ValueError('Sea source must be a port')
            if not target.coastal:
                raise ValueError('Sea target must be coastal')
        elif target.id not in source.neighbours:
            raise ValueError('Land target must be adjacent')
    if sum(order.kind == 'reserve' for order in orders) > context.level:
        raise ValueError('Reserve capacity exceeded')
    attacks = {order.territory_id for order in orders if order.kind == 'attack'}
    if len(attacks) > attack_limit(len(owned)):
        raise ValueError('Attack limit exceeded')
    ambushes = [order for order in orders if order.kind == 'ambush']
    if len(ambushes) > 2 or len({o.territory_id for o in ambushes}) > 1:
        raise ValueError('Only one ambush of one or two players is allowed')
    ordinary_targets = {o.territory_id for o in orders if o.kind in {'attack', 'defend'}}
    if any(o.territory_id not in ordinary_targets for o in ambushes):
        raise ValueError('Ambush requires an ordinary squad at its destination')
    return orders


def fill_defence_template(manual, template, context):
    orders = list(manual)
    assigned = {o.user_id for o in orders}
    owned = {t.id for t in context.territories if t.owner_clan_id == context.clan_id}
    for user_id, territory_id in sorted(template.items()):
        if (user_id in context.member_ids and user_id not in context.scouting_ids
                and user_id not in assigned and territory_id in owned):
            orders.append(Order(user_id, 'defend', territory_id))
            assigned.add(user_id)
    return validate_plan(orders, context)
