import pytest

from app.services.cycle_starting_lands import validate_starting_triple, qualifies_for_starting_slot
from app.services.cycle_orders import TerritoryState


def lands():
    return (
        TerritoryState(1, 1, neighbours=frozenset({2})),
        TerritoryState(2, 1, neighbours=frozenset({1, 3})),
        TerritoryState(3, None, neighbours=frozenset({2, 4})),
        TerritoryState(4, None, neighbours=frozenset({3, 5})),
        TerritoryState(5, None, neighbours=frozenset({4, 6})),
        TerritoryState(6, None, neighbours=frozenset({5}), port=True),
        TerritoryState(7, None, fortress=True),
        TerritoryState(8, 2, neighbours=frozenset({4})),
    )


def test_two_retained_lands_are_completed_with_one_neutral_connected_land():
    assert validate_starting_triple((1, 2, 3), clan_id=1, initial_owned={1, 2}, territories=lands()) == (1, 2, 3)


def test_retention_cannot_be_discarded_if_it_can_be_completed():
    with pytest.raises(ValueError, match='retain'):
        validate_starting_triple((3, 4, 5), clan_id=1, initial_owned={1, 2}, territories=lands())


@pytest.mark.parametrize('selection', [(1, 2), (1, 2, 2), (3, 4, 6), (3, 4, 7), (3, 4, 8), (1, 2, 5)])
def test_invalid_triples_ports_fortresses_occupied_or_disconnected(selection):
    with pytest.raises(ValueError):
        validate_starting_triple(selection, clan_id=3, initial_owned=set(), territories=lands())


def test_new_clan_can_choose_a_chain_not_only_all_pairwise_neighbours():
    assert validate_starting_triple((3, 4, 5), clan_id=3, initial_owned=set(), territories=lands()) == (3, 4, 5)


def test_impossible_retention_can_be_replaced_by_neutral_triple():
    world = lands() + (TerritoryState(9, 1),)
    assert validate_starting_triple((3, 4, 5), clan_id=1, initial_owned={9}, territories=world) == (3, 4, 5)


def test_existing_owner_reduces_to_connected_three_without_gift_quota():
    world = tuple(TerritoryState(t.id, 1 if t.id in {1, 2, 3, 4} else t.owner_clan_id,
                                 t.neighbours, t.coastal, t.port, t.fortress) for t in lands())
    assert validate_starting_triple((2, 3, 4), clan_id=1, initial_owned={1, 2, 3, 4}, territories=world) == (2, 3, 4)


def test_four_unique_verified_identities_are_needed_for_a_gift_slot():
    assert qualifies_for_starting_slot(['a', 'b', 'c', 'd'], already_used={'x'})
    assert not qualifies_for_starting_slot(['a', 'b', 'c', 'c'], already_used=set())
    assert not qualifies_for_starting_slot(['a', 'b', 'c', 'd'], already_used={'a'})
