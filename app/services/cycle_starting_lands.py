"""Starting-land validation; no map mutation or implicit choice of gifts."""

from itertools import combinations
from types import SimpleNamespace


def _connected(ids, world):
    ids = set(ids)
    if not ids:
        return False
    reached = {next(iter(ids))}
    pending = list(reached)
    while pending:
        current = pending.pop()
        for candidate in ids - reached:
            if candidate in world[current].neighbours or current in world[candidate].neighbours:
                reached.add(candidate)
                pending.append(candidate)
    return reached == ids


def selection_world(territories, initial_owners, resolved_clans):
    """Неподтверждённое прежнее право не является реальным владением карты."""
    result = {t.id: SimpleNamespace(id=t.id, owner_clan_id=t.owner_clan_id,
        neighbours=t.neighbours, port=t.port, fortress=t.fortress) for t in territories}
    reserved = {}
    for territory in result.values():
        owner = initial_owners.get(str(territory.id))
        if territory.owner_clan_id is None and owner is not None and owner not in resolved_clans and not territory.port and not territory.fortress:
            reserved.setdefault(owner, set()).add(territory.id)
    # Непригодные разрозненные прежние владения не блокируют замену нейтральной тройкой.
    for owner, owned in list(reserved.items()):
        if len(owned) >= 3 and not any(_connected(ids, result) for ids in combinations(sorted(owned), 3)):
            reserved.pop(owner)
    for owner, owned in list(reserved.items()):
        if len(owned) >= 3:
            continue
        blocked = set().union(*(ids for other, ids in reserved.items() if other != owner)) if reserved else set()
        neutral = [t.id for t in result.values() if t.owner_clan_id is None and t.id not in blocked | owned and not t.port and not t.fortress]
        if not any(_connected(owned | set(extra), result) for extra in combinations(neutral, 3 - len(owned))):
            reserved.pop(owner)
    for owner, ids in reserved.items():
        for territory_id in ids:
            result[territory_id].owner_clan_id = owner
    return list(result.values())


def validate_starting_triple(selected, *, clan_id, initial_owned, territories):
    selected = tuple(selected)
    world = {t.id: t for t in territories}
    if len(selected) != 3 or len(set(selected)) != 3 or any(t not in world for t in selected):
        raise ValueError('Exactly three distinct existing territories required')
    initial_owned = set(initial_owned)
    legal = {t.id for t in world.values() if not t.port and not t.fortress
             and (t.owner_clan_id is None or (t.id in initial_owned and t.owner_clan_id == clan_id))}
    if not set(selected) <= legal or not _connected(selected, world):
        raise ValueError('Starting lands must be connected, available, non-port and non-fortress')
    retained = {i for i in initial_owned & legal if world[i].owner_clan_id == clan_id}
    neutral = {i for i in legal if world[i].owner_clan_id is None}
    if retained:
        if len(retained) >= 3:
            feasible = any(_connected(ids, world) for ids in combinations(sorted(retained), 3))
            respects_retention = set(selected) <= retained
        else:
            feasible = any(_connected(retained | set(extra), world)
                           for extra in combinations(sorted(neutral), 3 - len(retained)))
            respects_retention = retained <= set(selected)
        if feasible and not respects_retention:
            raise ValueError('Must retain existing eligible land when a connected triple is possible')
        if not feasible and not set(selected) <= neutral:
            raise ValueError('Impossible retention must be replaced by an available neutral triple')
    return tuple(sorted(selected))


def qualifies_for_starting_slot(selected_identities, *, already_used):
    identities = tuple(selected_identities)
    return (len(identities) == 4 and len(set(identities)) == 4
            and all(isinstance(identity, str) and identity.strip() for identity in identities)
            and not set(identities) & set(already_used))
