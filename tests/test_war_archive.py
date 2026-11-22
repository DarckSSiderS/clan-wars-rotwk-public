from datetime import datetime, timedelta, timezone

from app.models.war import ClanWar
from app.services.war_service import ClanWarService


def test_general_war_journal_keeps_completed_wars(db):
    now = datetime.now(timezone.utc)
    db.add_all(
        [
            ClanWar(
                territory_id=1,
                attacking_clan_id=1,
                defending_clan_id=2,
                war_type="territory_attack",
                status="completed",
                started_at=now - timedelta(days=8),
                ended_at=now - timedelta(days=4),
            ),
            ClanWar(
                territory_id=2,
                attacking_clan_id=2,
                defending_clan_id=1,
                war_type="territory_attack",
                status="canceled",
                started_at=now - timedelta(days=12),
                ended_at=now - timedelta(days=11),
            ),
        ]
    )
    db.commit()

    wars = ClanWarService().get_wars(db, limit=100)

    assert [war.status for war in wars] == ["completed", "canceled"]
    assert all(war.ended_at is not None for war in wars)
