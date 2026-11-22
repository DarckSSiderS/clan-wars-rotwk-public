from datetime import timedelta

import pytest

from app.core.exceptions import InsufficientPermissionsException
from app.core.time import as_utc, utc_now
from app.models.clan import Clan, ClanMember
from app.models.clan_asset import ClanAsset, ClanOwnedAsset
from app.models.user import User
from app.services.clan_economy_service import ClanEconomyService


def _clan_with_relics(db, count=5):
    leader = User(
        username="relic-leader",
        email="relic-leader@example.test",
        hashed_password="x",
    )
    db.add(leader)
    db.flush()
    clan = Clan(name="Relic keep", leader_id=leader.id)
    db.add(clan)
    db.flush()
    db.add(ClanMember(user_id=leader.id, clan_id=clan.id, rank="Лидер"))
    owned = []
    for index in range(count):
        asset = ClanAsset(
            key=f"loadout_relic_{index}",
            name=f"Relic {index}",
            bonus_type="attack_power",
            bonus_value=index + 1,
        )
        db.add(asset)
        db.flush()
        item = ClanOwnedAsset(
            clan_id=clan.id,
            asset_id=asset.id,
            purchased_by=leader.id,
            level=1,
            is_active=False,
        )
        db.add(item)
        owned.append(item)
    db.commit()
    return clan, leader, owned


def test_leader_selects_up_to_four_active_relics(db):
    clan, leader, owned = _clan_with_relics(db)
    service = ClanEconomyService()

    result = service.update_relic_loadout(
        db,
        clan.id,
        [item.asset_id for item in owned[:4]],
        leader,
    )

    assert result["slots"] == 4
    assert set(result["asset_ids"]) == {item.asset_id for item in owned[:4]}
    assert service.get_relic_bonuses(db, clan.id)["attack_power"] == 10
    db.refresh(clan)
    assert as_utc(clan.relic_loadout_locked_until) > utc_now()


def test_changed_loadout_is_locked_for_two_days_but_same_selection_is_idempotent(db):
    clan, leader, owned = _clan_with_relics(db)
    service = ClanEconomyService()
    selected = [owned[0].asset_id]
    first = service.update_relic_loadout(db, clan.id, selected, leader)

    same = service.update_relic_loadout(db, clan.id, selected, leader)
    assert same["locked_until"] == first["locked_until"]

    with pytest.raises(InsufficientPermissionsException, match="заблокирован"):
        service.update_relic_loadout(db, clan.id, [owned[1].asset_id], leader)

    db.refresh(clan)
    assert as_utc(clan.relic_loadout_locked_until) <= utc_now() + timedelta(days=2, seconds=2)


def test_loadout_rejects_more_than_four_relics(db):
    clan, leader, owned = _clan_with_relics(db)

    with pytest.raises(InsufficientPermissionsException, match="не более 4"):
        ClanEconomyService().update_relic_loadout(
            db,
            clan.id,
            [item.asset_id for item in owned],
            leader,
        )
