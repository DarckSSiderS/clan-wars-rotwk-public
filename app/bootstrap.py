import logging

from app.database import SessionLocal
from app.services.bootstrap_service import (
    ensure_campaign_rules,
    ensure_admin_test_clan,
    ensure_default_admin,
    ensure_progression_content,
    ensure_shop_content,
)
from app.services.user_service import UserService
from app.config import settings


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_bootstrap() -> None:
    with SessionLocal() as db:
        ensure_default_admin(
            db,
            create_account=settings.BOOTSTRAP_TEST_ADMIN_ENABLED,
        )
        ensure_progression_content(db)
        ensure_shop_content(db)
        ensure_campaign_rules(db)
        admin_clan = (
            ensure_admin_test_clan(db)
            if settings.BOOTSTRAP_TEST_ADMIN_ENABLED
            else None
        )
        created_profiles = UserService().ensure_ladder_profiles(db)
        logger.info(
            "Bootstrap completed; admin clan=%s, ladder profiles created=%s",
            admin_clan.name if admin_clan else "disabled",
            created_profiles,
        )


if __name__ == "__main__":
    run_bootstrap()
