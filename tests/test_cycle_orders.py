import pytest

from app.services.cycle_orders import Order, PlanningContext, TerritoryState, validate_plan, fill_defence_template


def context(**changes):
    values = dict(clan_id=1, level=2, influence=500, member_ids=frozenset({1, 2, 3, 4}),
                  reserve_blocked_ids=frozenset(),
                  territories=(TerritoryState(1, 1, neighbours=frozenset({2, 3})),
                               TerritoryState(2, None), TerritoryState(3, 2),
                               TerritoryState(4, None), TerritoryState(5, 2, coastal=True)),
                  allied_clan_ids=frozenset())
    values.update(changes)
    return PlanningContext(**values)


def test_single_member_squad_and_multiple_clans_can_target_same_territory():
    plan = validate_plan([Order(1, 'attack', 3, source_id=1)], context())
    assert len(plan) == 1


def test_one_member_cannot_have_two_assignments():
    with pytest.raises(ValueError, match='duplicate'):
        validate_plan([Order(1, 'attack', 2, source_id=1), Order(1, 'reserve')], context())


def test_membership_and_reserve_capacity_are_checked():
    with pytest.raises(ValueError, match='member'):
        validate_plan([Order(9, 'reserve')], context())
    with pytest.raises(ValueError, match='capacity'):
        validate_plan([Order(1, 'reserve'), Order(2, 'reserve'), Order(3, 'reserve')], context())
    with pytest.raises(ValueError, match='cooldown'):
        validate_plan([Order(1, 'reserve')], context(reserve_blocked_ids=frozenset({1})))


def test_attack_limit_counts_destinations_not_players():
    validate_plan([Order(1, 'attack', 2, source_id=1), Order(2, 'attack', 2, source_id=1),
                   Order(3, 'attack', 3, source_id=1)], context())
    with pytest.raises(ValueError, match='limit'):
        validate_plan([Order(1, 'attack', 2), Order(2, 'attack', 3), Order(3, 'attack', 4)],
                      context(territories=tuple(TerritoryState(i, None) for i in range(1, 6))))


def test_defence_requires_owned_land_and_cannot_consume_attack_quota():
    validate_plan([Order(1, 'defend', 1), Order(2, 'defend', 1)], context())
    with pytest.raises(ValueError, match='owned'):
        validate_plan([Order(1, 'defend', 2)], context())


def test_normal_land_attack_requires_snapshot_neighbour_source():
    with pytest.raises(ValueError, match='adjacent'):
        validate_plan([Order(1, 'attack', 4, source_id=1)], context())
    with pytest.raises(ValueError, match='source'):
        validate_plan([Order(1, 'attack', 2, source_id=3)], context())


def test_port_allows_coastal_target_without_target_port():
    port = TerritoryState(1, 1, port=True)
    ctx = context(territories=(port, TerritoryState(2, 2, coastal=True), TerritoryState(3, 2)))
    validate_plan([Order(1, 'attack', 2, source_id=1, route='sea')], ctx)
    with pytest.raises(ValueError, match='coastal'):
        validate_plan([Order(1, 'attack', 3, source_id=1, route='sea')], ctx)


def test_landless_can_attack_anywhere_except_ports_and_fortresses():
    ctx = context(territories=(TerritoryState(1, 2), TerritoryState(2, None),
                               TerritoryState(3, 2, port=True), TerritoryState(4, None, fortress=True)))
    validate_plan([Order(1, 'attack', 1), Order(2, 'attack', 2)], ctx)
    for target in (3, 4):
        with pytest.raises(ValueError, match='landless'):
            validate_plan([Order(1, 'attack', target)], ctx)


def test_fortress_requires_five_lands_and_350_influence():
    lands = tuple(TerritoryState(i, 1, neighbours=frozenset({9})) for i in range(1, 6))
    ctx = context(territories=lands + (TerritoryState(9, 2, fortress=True),), influence=350)
    validate_plan([Order(1, 'attack', 9, source_id=1)], ctx)
    with pytest.raises(ValueError, match='fortress'):
        validate_plan([Order(1, 'attack', 9, source_id=1)], context(territories=ctx.territories, influence=349))


def test_cannot_attack_ally_or_own_land():
    with pytest.raises(ValueError):
        validate_plan([Order(1, 'attack', 1, source_id=1)], context())
    with pytest.raises(ValueError, match='ally'):
        validate_plan([Order(1, 'attack', 3, source_id=1)], context(allied_clan_ids=frozenset({2})))


def test_one_ambush_group_up_to_two_people_and_must_have_opposing_ordinary_squad():
    validate_plan([Order(1, 'attack', 3, source_id=1), Order(2, 'ambush', 3)], context())
    with pytest.raises(ValueError, match='ordinary'):
        validate_plan([Order(1, 'ambush', 3)], context())
    with pytest.raises(ValueError, match='ambush'):
        validate_plan([Order(1, 'attack', 3, source_id=1), Order(2, 'ambush', 3),
                       Order(3, 'ambush', 3), Order(4, 'ambush', 3)], context())


def test_defence_template_only_fills_unassigned_existing_members_and_owned_lands():
    manual = [Order(1, 'reserve')]
    filled = fill_defence_template(manual, {1: 1, 2: 1, 3: 2, 9: 1}, context())
    assert filled == (Order(1, 'reserve'), Order(2, 'defend', 1))


def test_invalid_order_kind_or_unknown_territory_is_rejected():
    for order in (Order(1, 'invented', 1), Order(1, 'attack', 999, source_id=1)):
        with pytest.raises(ValueError):
            validate_plan([order], context())
