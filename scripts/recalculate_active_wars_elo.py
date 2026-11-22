import asyncio
import logging

import aiohttp

from app.database import SessionLocal
from app.models.war import ClanWar, ClanWarMatchResult
from app.services.ladder_service import BFMELadderService
from app.services.war_service import ClanWarService


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def capture_missing_ratings(db, wars):
    ladder = BFMELadderService()
    cache = {}
    timeout = aiohttp.ClientTimeout(total=45, connect=15)
    results = (
        db.query(ClanWarMatchResult)
        .filter(ClanWarMatchResult.war_id.in_([war.id for war in wars]))
        .order_by(ClanWarMatchResult.played_at)
        .all()
    )

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for index, result in enumerate(results, start=1):
            match = result.match
            if (
                match.winner_elo is not None
                and match.loser_elo is not None
                and match.rating_patch_family is not None
            ):
                continue
            replay = {
                "PatchName": match.patch_name or match.patch_version,
                "PatchId": match.patch_id,
            }
            snapshot = await ladder._capture_match_ratings(
                session,
                replay,
                result.winner_user.username,
                result.loser_user.username,
                cache,
            )
            if not snapshot:
                continue
            match.winner_elo = snapshot["winner_elo"]
            match.loser_elo = snapshot["loser_elo"]
            match.rating_patch_family = snapshot["patch_family"]
            match.ratings_captured_at = snapshot["captured_at"]
            match.rating_source = "bfmeladder_profile_current"
            if index % 20 == 0:
                db.commit()
    db.commit()
    logger.info(
        "Elo snapshots prepared for %s matches using %s cached profiles",
        len(results),
        len(cache),
    )


async def main():
    db = SessionLocal()
    try:
        wars = db.query(ClanWar).filter(ClanWar.status == "active").all()
        if not wars:
            logger.info("No active wars to recalculate")
            return
        await capture_missing_ratings(db, wars)
        service = ClanWarService()
        for war in wars:
            result = service.recalculate_active_war(db, war.id)
            logger.info("Recalculated war %s: %s", war.id, result)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
