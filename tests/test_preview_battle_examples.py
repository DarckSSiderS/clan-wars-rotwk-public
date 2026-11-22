import pytest

from tests.test_preview_campaign_seed import preview, seeder, scenarios, rows, digest
from app.services.preview_battle_examples import add_preview_battle_examples


def test_examples_use_real_scoring_preserve_cycle_wallets_and_are_idempotent(preview):
    seeder().seed_preview(preview, worker_disabled=True)
    scenarios().switch_preview_scenario(preview, 'battle')
    cycle_query = 'select id,season_id,number,starts_at,preparation_at,orders_frozen_at,settled_at,battles_registered,planning_snapshot from campaign_cycles order by id'
    cycle_before = rows(preview, cycle_query)
    wallet_before = rows(preview, 'select * from cycle_economy_states order by id')
    result = add_preview_battle_examples(preview)
    assert result['created'] == 3
    assert result['counted'] > 0 and result['rejected'] == 2
    assert rows(preview, cycle_query) == cycle_before
    assert rows(preview, 'select * from cycle_economy_states order by id') == wallet_before
    before = digest(preview)
    assert add_preview_battle_examples(preview)['created'] == 0
    assert digest(preview) == before


def test_examples_refuse_unseeded_database_without_changes(preview):
    before = digest(preview)
    with pytest.raises(ValueError):
        add_preview_battle_examples(preview)
    assert digest(preview) == before
