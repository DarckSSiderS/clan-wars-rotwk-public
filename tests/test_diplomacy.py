import pytest
from fastapi import HTTPException

from app.models.clan import Clan, ClanMember
from app.models.diplomacy import ClanDiplomacyEvent, ClanDiplomaticRelation
from app.models.notification import UserNotification
from app.models.user import User
from app.services.diplomacy_service import ClanDiplomacyService
from app.services.war_service import clans_are_allied


def _seed_clans(db):
    first_user = User(
        id=1,
        username="RohanLeader",
        email="rohan@example.test",
        hashed_password="unused",
        is_claimed=True,
    )
    second_user = User(
        id=2,
        username="GondorLeader",
        email="gondor@example.test",
        hashed_password="unused",
        is_claimed=True,
    )
    outsider = User(
        id=3,
        username="Outsider",
        email="outsider@example.test",
        hashed_password="unused",
        is_claimed=True,
    )
    db.add_all([first_user, second_user, outsider])
    db.flush()
    first_clan = Clan(id=10, name="Rohan", leader_id=first_user.id, map_color="#6F815C")
    second_clan = Clan(id=20, name="Gondor", leader_id=second_user.id, map_color="#8C8F88")
    db.add_all([first_clan, second_clan])
    db.flush()
    db.add_all([
        ClanMember(user_id=first_user.id, clan_id=first_clan.id, rank="Лидер"),
        ClanMember(user_id=second_user.id, clan_id=second_clan.id, rank="Лидер"),
    ])
    db.commit()
    return first_user, second_user, outsider, first_clan, second_clan


def test_alliance_proposal_acceptance_and_audit(db):
    first_user, second_user, _, first_clan, second_clan = _seed_clans(db)
    service = ClanDiplomacyService()

    proposed = service.act(
        db,
        actor_clan_id=first_clan.id,
        other_clan_id=second_clan.id,
        actor=first_user,
        action="propose_alliance",
        note="Защитим запад вместе",
    )
    assert proposed["status"] == "pending_alliance"
    assert proposed["requested_by_clan_id"] == first_clan.id

    accepted = service.act(
        db,
        actor_clan_id=second_clan.id,
        other_clan_id=first_clan.id,
        actor=second_user,
        action="accept_alliance",
    )
    assert accepted["status"] == "allied"
    assert accepted["requested_by_clan_id"] is None
    assert db.query(ClanDiplomaticRelation).count() == 1
    assert db.query(ClanDiplomacyEvent).count() == 2
    assert db.query(UserNotification).count() == 2
    assert clans_are_allied(db, first_clan.id, second_clan.id) is True


def test_repeated_diplomacy_action_is_idempotent_and_public_list_hides_notes(db):
    first_user, _, _, first_clan, second_clan = _seed_clans(db)
    service = ClanDiplomacyService()

    first = service.act(
        db,
        actor_clan_id=first_clan.id,
        other_clan_id=second_clan.id,
        actor=first_user,
        action="propose_alliance",
        note="Закрытое послание",
    )
    repeated = service.act(
        db,
        actor_clan_id=first_clan.id,
        other_clan_id=second_clan.id,
        actor=first_user,
        action="propose_alliance",
        note="Повтор",
    )

    assert repeated["id"] == first["id"]
    assert db.query(ClanDiplomacyEvent).count() == 1
    assert db.query(UserNotification).count() == 1
    assert service.list_relations(db, clan_id=first_clan.id)[0]["events"] == []


def test_only_clan_manager_can_change_diplomacy(db):
    _, _, outsider, first_clan, second_clan = _seed_clans(db)

    with pytest.raises(HTTPException) as error:
        ClanDiplomacyService().act(
            db,
            actor_clan_id=first_clan.id,
            other_clan_id=second_clan.id,
            actor=outsider,
            action="declare_hostility",
        )

    assert error.value.status_code == 403


@pytest.mark.parametrize('mode', ['interseason', 'cycle_v1'])
def test_legacy_diplomacy_is_hidden_and_read_only_outside_legacy_campaign(db, mode):
    from app.models.campaign import CampaignSeason
    from app.core.time import utc_now
    first, _, _, low, high = _seed_clans(db)
    service = ClanDiplomacyService()
    service.act(db, actor_clan_id=low.id, other_clan_id=high.id, actor=first, action='propose_alliance')
    db.add(CampaignSeason(number=1, name='Тестовый сезон', status='completed' if mode=='interseason' else 'active',
        starts_at=utc_now(), rules_snapshot={'mechanics_version':'legacy' if mode=='interseason' else 'cycle_v1'}))
    db.commit()
    before = [(row.status, row.requested_by_clan_id, row.updated_at) for row in db.query(ClanDiplomaticRelation)]
    assert service.list_relations(db) == []
    assert service.list_relations(db, include_neutral=True, clan_id=low.id) == []
    with pytest.raises(HTTPException) as error:
        service.act(db, actor_clan_id=low.id, other_clan_id=high.id, actor=first, action='declare_hostility')
    assert error.value.status_code == 409
    assert [(row.status, row.requested_by_clan_id, row.updated_at) for row in db.query(ClanDiplomaticRelation)] == before
    assert db.query(ClanDiplomacyEvent).count() == db.query(UserNotification).count() == 1
