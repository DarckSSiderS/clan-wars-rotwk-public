from unittest.mock import Mock

import pytest

from app.models.clan import Clan, ClanApplication
from app.models.user import User
from app.schemas.clan import ClanApplicationCreate
from app.services.clan_service import ClanService, notification_service


@pytest.mark.parametrize('status', ['pending', 'accepted', 'declined'])
def test_application_retry_preserves_existing_request(db, monkeypatch, status):
    user = User(username='applicant', email='applicant@example.test', hashed_password='x')
    leader = User(username='leader', email='leader@example.test', hashed_password='x')
    db.add_all([user, leader])
    db.flush()
    clan = Clan(name='Test clan', leader_id=leader.id, is_recruiting=True)
    db.add(clan)
    db.flush()
    original = ClanApplication(clan_id=clan.id, user_id=user.id, message='Original', status=status)
    db.add(original)
    db.commit()
    notify = Mock()
    monkeypatch.setattr(notification_service, 'create', notify)

    result = ClanService().create_clan_application(
        db, clan.id, ClanApplicationCreate(message='Retry'), user.id,
    )

    if status == 'pending':
        assert result is not None
        assert result.id == original.id
        assert result.status == 'pending'
    else:
        assert result is None
    assert db.query(ClanApplication).count() == 1
    assert original.message == 'Original'
    notify.assert_not_called()
