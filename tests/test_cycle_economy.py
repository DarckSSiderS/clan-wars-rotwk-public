"""Pure domain tests: intentionally avoid application imports and DB fixtures."""

import importlib.util
from pathlib import Path
import sys
from decimal import Decimal as D

import pytest


@pytest.fixture
def economy():
    path = Path(__file__).parents[1] / 'app/services/cycle_economy.py'
    assert path.exists(), 'New-season pure economy module is missing'
    spec = importlib.util.spec_from_file_location('isolated_cycle_economy', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_start_and_unconditional_daily_income(economy):
    e = economy
    assert e.START_RESOURCES == e.Resources(1000, 30, 30, 20, 5)
    assert e.BASE_DAILY_INCOME == e.Resources(100, 2, 2, 2, 0)
    assert isinstance(e.START_RESOURCES.gold, D)


@pytest.mark.parametrize('resource,buy,sell', [('iron', 45, 10), ('wood', 40, 8),
                                             ('food', 30, 6), ('mithril', 300, 60)])
def test_market_exact_prices_and_no_input_mutation(economy, resource, buy, sell):
    e = economy
    wallet = e.Resources(1000, 10, 10, 10, 10)
    bought = e.system_market(wallet, resource, D('1.5'), buying=True)
    sold = e.system_market(wallet, resource, D('1.5'), buying=False)
    assert bought.gold == 1000 - D('1.5') * buy
    assert getattr(bought, resource) == D('11.5')
    assert sold.gold == 1000 + D('1.5') * sell
    assert getattr(sold, resource) == D('8.5')
    assert wallet == e.Resources(1000, 10, 10, 10, 10)


def test_barter_fees_and_cargo_are_not_instant_delivery(economy):
    e = economy
    a, b = e.Resources(120, 20), e.Resources(90, wood=30)
    result = e.accept_barter(a, b, e.Resources(iron=20), e.Resources(wood=30))
    assert result.first_fee == 120
    assert result.second_fee == 90
    assert result.first_balance == result.second_balance == e.Resources()
    assert result.to_first == e.Resources(wood=30)
    assert result.to_second == e.Resources(iron=20)
    assert e.barter_fee(e.Resources(food='0.01')) == D('0.03')


def test_insufficient_second_party_never_debits_first(economy):
    e = economy
    a, b = e.Resources(120, 20), e.Resources(89, wood=30)
    with pytest.raises(e.InsufficientFunds):
        e.accept_barter(a, b, e.Resources(iron=20), e.Resources(wood=30))
    assert a == e.Resources(120, 20)
    assert b == e.Resources(89, wood=30)
    with pytest.raises(e.InsufficientFunds):
        e.system_market(e.Resources(44), 'iron', 1, buying=True)


@pytest.mark.parametrize('kwargs', [{'first_at_war': True}, {'second_at_war': True},
                                   {'first_has_land': False}, {'second_has_land': False},
                                   {'route_available': False}])
def test_barter_current_eligibility(economy, kwargs):
    e = economy
    with pytest.raises(ValueError):
        e.accept_barter(e.Resources(100, iron=1), e.Resources(100, wood=1),
                        e.Resources(iron=1), e.Resources(wood=1), **kwargs)


@pytest.mark.parametrize('value', [-1, 'NaN', 'Infinity', 0.1, True])
def test_resource_validation(economy, value):
    with pytest.raises((ValueError, TypeError)):
        economy.Resources(gold=value)


def test_invalid_trade_values(economy):
    e = economy
    for resource, quantity in [('gold', 1), ('iron', 0), ('wood', -1), ('food', 'NaN')]:
        with pytest.raises((ValueError, TypeError)):
            e.system_market(e.START_RESOURCES, resource, quantity, buying=True)
    for cargo in [e.Resources(), e.Resources(gold=1, iron=1)]:
        with pytest.raises(ValueError):
            e.barter_fee(cargo)


@pytest.mark.parametrize('branch,costs,effects', [
    ('gold', [(300,5,10,5,0),(1000,15,25,15,0),(2500,30,50,30,3)], [35,115,265]),
    ('profile', [(200,5,10,5,0),(600,15,20,10,0),(1500,30,40,25,2)], [2,5,10]),
    ('mithril', [(400,10,10,10,1),(1200,25,20,20,3),(3000,50,40,35,6)], ['0.5','1.25','2.5']),
    ('fortification', [(500,15,10,5,0),(1500,35,25,10,2),(3500,70,50,20,5)], [5,10,20]),
    ('offense', [(500,15,5,15,0),(1500,35,15,35,2),(3500,70,30,70,5)], [5,10,20]),
    ('naval', [(600,10,25,10,0),(1800,25,60,25,2),(4000,50,120,50,5)], [5,10,20]),
])
def test_all_upgrade_tables(economy, branch, costs, effects):
    e = economy
    for level, (cost, effect) in enumerate(zip(costs, effects), 1):
        assert e.upgrade_cost(branch, level - 1) == e.Resources(*cost)
        assert e.upgrade_effect(branch, level) == D(str(effect))
    assert e.upgrade_effect(branch, 0) == 0
    with pytest.raises(ValueError):
        e.upgrade_cost(branch, 3)


def test_discount_scope_and_snapshot_survives_collection_upgrade(economy):
    e = economy
    owned = {'merchant_guild': 3, 'ring_of_barahir': 3, 'white_tree': 1}
    snapshot = e.relic_snapshot(owned, owned)
    assert e.upgrade_cost('gold', 0, snapshot) == e.Resources(210, 5, 10, 5)
    assert e.upgrade_cost('fortification', 0, snapshot) == e.Resources(500, '10.5', 7, 5)
    assert e.upgrade_cost('offense', 0, snapshot) == e.Resources(500, 15, 5, 15)
    wallet = e.Resources(100000, 1000, 1000, 1000, 1000)
    remaining, updated = e.buy_relic(wallet, owned, 'white_tree')
    assert updated['white_tree'] == 2
    assert owned['white_tree'] == 1
    assert remaining == e.debit(wallet, e.Resources(1000, 10, 15, 10, 2))
    assert e.territory_income(e.Resources(100, iron=4), 'iron', gold_level=1,
                              profile_level=2, snapshot=snapshot) == e.Resources('155.25', 9)
    assert e.relic_snapshot(updated, updated) != snapshot


def test_income_preserves_fraction_and_never_creates_resource(economy):
    e = economy
    snap = e.relic_snapshot({'galadhrim_mirror': 3}, ['galadhrim_mirror'])
    assert e.territory_income(e.Resources(100, mithril=1), 'mithril',
                              profile_level=3, snapshot=snap) == e.Resources(100, mithril='4.725')
    snap = e.relic_snapshot({'dwarf_anvil': 3}, ['dwarf_anvil'])
    assert e.territory_income(e.Resources(100, wood=4), 'wood', profile_level=2,
                              snapshot=snap) == e.Resources(100, wood=9)
    with pytest.raises(ValueError):
        e.territory_income(e.Resources(100), 'mithril', profile_level=1)
    with pytest.raises(ValueError):
        e.territory_income(e.Resources(100, iron=4, wood=4), 'iron')


def test_relic_catalog_stable_identity_and_free_distinct_gifts(economy):
    e = economy
    assert len(e.RELICS) == 15
    assert e.RELICS['mordor_forge'].name == 'Житницы Нурна'
    assert e.RELICS['merchant_guild'].costs[1] == e.Resources(300,5,10,5,1)
    assert e.RELICS['galadhrim_mirror'].effects == (D(15), D(25), D(35))
    assert e.starting_relics(['mordor_forge', 'white_tree']) == {'mordor_forge': 1, 'white_tree': 1}
    for keys in [[], ['white_tree'], ['white_tree', 'white_tree'], ['unknown', 'white_tree']]:
        with pytest.raises(ValueError):
            e.starting_relics(keys)


def test_relic_purchase_is_sequential_permanent_and_needs_no_influence(economy):
    e = economy
    wallet = e.Resources(100000, 1000, 1000, 1000, 1000)
    owned = {}
    for level in range(1, 4):
        before = wallet
        wallet, owned = e.buy_relic(wallet, owned, 'war_foundry')
        assert owned == {'war_foundry': level}
        assert wallet == e.debit(before, e.RELICS['war_foundry'].costs[level - 1])
    with pytest.raises(ValueError):
        e.buy_relic(wallet, owned, 'war_foundry')
    with pytest.raises(e.InsufficientFunds):
        e.buy_relic(e.Resources(), {}, 'war_foundry')


def test_loadout_rules_and_immutable_snapshots(economy):
    e = economy
    owned = {key: 1 for key in e.RELICS}
    selected = list(owned)[:4]
    snap = e.relic_snapshot(owned, selected)
    owned[selected[0]] = 3
    assert snap[0].level == 1
    for selection in [list(owned)[:5], ['unknown'], [selected[0]] * 2]:
        with pytest.raises(ValueError):
            e.relic_snapshot(owned, selection)
    with pytest.raises(ValueError):
        e.relic_snapshot({}, selected)
    assert e.select_relics(owned, selected, phase='rest') == tuple(selected)
    assert e.select_relics(owned, selected, phase='preparation') == tuple(selected)
    with pytest.raises(ValueError):
        e.select_relics(owned, selected, phase='battle')
    with pytest.raises((AttributeError, TypeError)):
        snap[0].level = 2


def test_victory_conditions_cap_and_interception_is_separate(economy):
    e = economy
    snap = e.relic_snapshot({'war_foundry':3, 'mithril_standard':3, 'palantir':3,
                             'red_arrow':3}, ['war_foundry','mithril_standard','palantir','red_arrow'])
    assert e.victory_bonus(snap, role='attack', offense_level=3) == 50
    assert e.victory_bonus(snap, role='attack', offense_level=3, won=False) == 0
    assert e.victory_bonus(snap, role='interception', offense_level=3, fortress=True) == 40
    assert e.victory_bonus((), role='attack', offense_level=3, naval=True, naval_level=1) == 5
    assert e.victory_bonus((), role='defense', fortification_level=3, fortress=True) == 30
    snap = e.relic_snapshot({'helms_horn':3}, ['helms_horn'])
    assert e.victory_bonus(snap, role='defense') == 0
    assert e.victory_bonus(snap, role='defense', direct=True) == 40


@pytest.mark.parametrize('level', [-1, 4, True, D('1.5')])
def test_invalid_levels_rejected(economy, level):
    with pytest.raises(ValueError):
        economy.upgrade_effect('gold', level)
    with pytest.raises(ValueError):
        economy.relic_snapshot({'white_tree': level}, ['white_tree'])


@pytest.mark.parametrize('key,effects,costs', [
    ('royal_charter', (15,25,35), ((2500,10,25,15,3),(5000,20,50,30,6),(10000,40,100,60,12))),
    ('war_foundry', (10,15,20), ((3000,30,15,15,4),(6000,60,30,30,8),(12000,120,60,60,16))),
    ('mithril_standard', (15,25,35), ((3500,30,15,20,6),(7000,60,30,40,12),(14000,120,60,80,24))),
    ('granite_bastion', (15,25,35), ((3500,35,25,10,6),(7000,70,50,20,12),(14000,140,100,40,24))),
    ('merchant_guild', (10,20,30), ((3000,10,30,20,4),(300,5,10,5,1),(700,10,15,10,2))),
    ('white_tree', (15,25,35), ((3000,15,25,20,4),(1000,10,15,10,2),(1800,20,25,20,3))),
    ('red_arrow', (20,30,40), ((2500,15,25,25,3),(5000,30,50,50,6),(10000,60,100,100,12))),
    ('iron_crown', (20,30,40), ((3000,35,15,15,4),(6000,70,30,30,8),(12000,140,60,60,16))),
    ('palantir', (20,30,40), ((3500,15,20,25,6),(7000,30,40,50,12),(14000,60,80,100,24))),
    ('dwarf_anvil', (20,35,50), ((3000,30,15,15,4),(900,15,10,10,2),(1600,25,20,15,3))),
    ('ents_seed', (20,35,50), ((3000,10,35,20,4),(800,10,15,10,2),(1400,20,25,15,3))),
    ('mordor_forge', (20,35,50), ((3000,25,20,30,4),(600,10,10,15,2),(1100,20,20,25,3))),
    ('helms_horn', (20,30,40), ((3000,25,25,20,4),(6000,50,50,40,8),(12000,100,100,80,16))),
    ('ring_of_barahir', (10,20,30), ((3500,25,20,20,6),(7000,50,40,40,12),(14000,100,80,80,24))),
    ('galadhrim_mirror', (15,25,35), ((4000,15,30,25,8),(700,10,15,10,2),(1400,20,25,20,3))),
])
def test_every_catalog_transition_matches_spec(economy, key, effects, costs):
    relic = economy.RELICS[key]
    assert relic.effects == tuple(map(D, effects))
    assert relic.costs == tuple(economy.Resources(*row) for row in costs)


@pytest.mark.parametrize('resource', ['gold', 'iron', 'wood', 'food', 'mithril'])
def test_missing_any_payment_component_is_atomic(economy, resource):
    e = economy
    values = dict.fromkeys(e.RESOURCE_NAMES, 100)
    values[resource] = 0
    balance = e.Resources(**values)
    before = e.Resources(**values)
    with pytest.raises(e.InsufficientFunds):
        e.debit(balance, e.Resources(1,1,1,1,1))
    assert balance == before


def test_tables_are_immutable_and_zero_loadout_has_no_effect(economy):
    e = economy
    with pytest.raises(TypeError):
        e.RELICS['new'] = e.RELICS['white_tree']
    with pytest.raises(TypeError):
        e.MARKET_BUY['iron'] = 0
    with pytest.raises((AttributeError, TypeError)):
        e.START_RESOURCES.gold = 0
    assert e.relic_snapshot({'white_tree':3}, []) == ()
    assert e.territory_income(e.Resources(100, wood=4), 'wood') == e.Resources(100, wood=4)


def test_discount_is_frozen_even_after_upgrade_and_does_not_discount_relics(economy):
    e = economy
    wallet = e.Resources(10000, 1000, 1000, 1000, 1000)
    owned = {'merchant_guild': 1}
    snap = e.relic_snapshot(owned, owned)
    after, updated = e.buy_relic(wallet, owned, 'merchant_guild')
    assert after == e.debit(wallet, e.Resources(300,5,10,5,1))
    assert e.upgrade_cost('gold', 0, snap).gold == 270
    assert e.upgrade_cost('gold', 0, e.relic_snapshot(updated, updated)).gold == 240


def test_gold_and_profile_income_document_examples(economy):
    e = economy
    snap = e.relic_snapshot({'white_tree':3,'dwarf_anvil':3}, ['white_tree','dwarf_anvil'])
    for level, gold, iron in [(1,'182.25',9),(2,'290.25','13.5'),(3,'492.75',21)]:
        assert e.territory_income(e.Resources(100,iron=4), 'iron', gold_level=level,
                                  profile_level=level, snapshot=snap) == e.Resources(gold,iron)


def test_allied_help_and_fortress_conditions(economy):
    e = economy
    snap = e.relic_snapshot({'red_arrow':1, 'iron_crown':1, 'granite_bastion':1},
                            ['red_arrow','iron_crown','granite_bastion'])
    assert e.victory_bonus(snap, role='defense') == 15
    assert e.victory_bonus(snap, role='defense', allied_help=True) == 35
    assert e.victory_bonus(snap, role='defense', fortress=True) == 45
    assert e.victory_bonus(snap, role='interception') == 0
