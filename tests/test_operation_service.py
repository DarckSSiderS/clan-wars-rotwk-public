import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from app.models.clan import Clan
from app.models.match import Match
from app.models.operation import ResourceLedgerEntry
from app.models.role import Role
from app.models.user import User
from app.services.operation_service import ResourceLedgerService


def test_resource_operation_is_idempotent(db):
    role = Role(name="user", description="User")
    user = User(
        id=1,
        username="leader",
        email="leader@example.test",
        hashed_password="unused",
        role=role,
    )
    clan = Clan(id=1, name="Ledger clan", leader_id=1, gold=100, resources=100)
    db.add_all([role, user, clan])
    db.commit()

    ledger = ResourceLedgerService()
    first, first_applied = ledger.apply_change(
        db,
        clan,
        resource="gold",
        amount=25,
        operation_id="income:day-1",
        action="test_income",
    )
    second, second_applied = ledger.apply_change(
        db,
        clan,
        resource="gold",
        amount=25,
        operation_id="income:day-1",
        action="test_income",
    )
    db.commit()

    assert first_applied is True
    assert second_applied is False
    assert second.id == first.id
    assert clan.gold == 125
    assert db.query(ResourceLedgerEntry).count() == 1


def test_resource_operation_rejects_negative_balance(db):
    role = Role(name="user", description="User")
    user = User(
        id=1,
        username="leader",
        email="leader@example.test",
        hashed_password="unused",
        role=role,
    )
    clan = Clan(id=1, name="Poor clan", leader_id=1, mithril=2)
    db.add_all([role, user, clan])
    db.commit()

    with pytest.raises(ValueError, match="Недостаточно ресурса"):
        ResourceLedgerService().apply_change(
            db,
            clan,
            resource="mithril",
            amount=-3,
            operation_id="purchase:1",
            action="test_purchase",
        )


def test_match_import_key_is_unique(db):
    fields = {
        "match_id": "replay-123",
        "winner_player": "Winner",
        "winner_faction": "Men",
        "loser_player": "Loser",
        "loser_faction": "Orcs",
        "match_date": datetime(2026, 7, 23, 12, 0),
    }
    db.add(Match(**fields))
    db.commit()
    db.add(Match(**fields))

    with pytest.raises(IntegrityError):
        db.commit()
