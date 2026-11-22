"""Current Arena ladder ratings, independent of local match-history preferences."""
import asyncio
import aiohttp

from app.services.elo_service import BfmeProfileRatingService


class ArenaCurrentRatingService:
    def __init__(self):
        self.loader = BfmeProfileRatingService()

    async def fetch_patch(self, patch):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            rows = await self.loader._fetch_ladder_ratings(session, patch)
            if rows:
                return rows
            cached = self.loader._ladder_cache.get(patch)
            return cached[1] if cached else []

    async def for_user(self, user):
        identities = [identity for identity in user.external_identities
                      if identity.source == 'bfmeladder'] if user else []
        if not identities:
            return {}
        uuids = {identity.external_uuid for identity in identities}
        patches = ('patch_202', 'ennorath')
        rows_by_patch = await asyncio.gather(*(self.fetch_patch(patch) for patch in patches))
        return {patch: rating for patch, rows in zip(patches, rows_by_patch)
                for _, player_uuid, rating in rows if player_uuid in uuids}


arena_current_ratings = ArenaCurrentRatingService()
