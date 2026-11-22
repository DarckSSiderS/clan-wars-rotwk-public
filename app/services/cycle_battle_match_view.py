"""Read-only, batched public match summaries for the territory battle feed."""

from sqlalchemy.orm import selectinload

from app.core.time import as_utc
from app.models.external_identity import ExternalPlayerIdentity
from app.models.match import Match
from app.models.user import User
from app.services.map_preview_storage_service import MapPreviewStorageService
from app.services.match_eligibility_service import RANKED_MODE_TEAM_SIZES


def _recorded_players(match, unknown_result):
    payload = match.source_payload if isinstance(match.source_payload, dict) else {}
    raw = payload.get('PublicApiPayload')
    if isinstance(raw, dict):
        from app.services.cycle_arena_ingestion_service import CycleArenaIngestionService
        try:
            facts = CycleArenaIngestionService.adapt(match)
        except ValueError:
            return []
        names = {player.get('uuid'): player for player in raw['players'] if isinstance(player, dict)}
        return [dict(uuid=player.uuid, name=names.get(player.uuid, {}).get('displayName') or names.get(player.uuid, {}).get('nickname') or '—',
                     faction=names.get(player.uuid, {}).get('factionName'), team=player.team,
                     is_winner=(player.team == facts.winning_team) if facts.winning_team is not None else None)
                for player in facts.players]
    recorded = [dict(uuid=p.player_uuid, name=p.nickname, faction=p.faction, team=p.team,
                     is_winner=None if unknown_result else p.is_winner)
                for p in match.participants if not p.is_observer]
    mode = ' '.join(str(match.gamemode_name or match.game_mode or '').lower().split())
    if not match.participants and RANKED_MODE_TEAM_SIZES.get(mode) == 1:
        recorded = [dict(uuid=match.winner_player_uuid, name=match.winner_player, faction=match.winner_faction, team=1, is_winner=None if unknown_result else True),
                    dict(uuid=match.loser_player_uuid, name=match.loser_player, faction=match.loser_faction, team=2, is_winner=None if unknown_result else False)]
    return recorded


def battle_match_summaries(db, contributions):
    references = {}
    historical_users = {}
    for row in contributions:
        reference = row.replay_id
        if reference.startswith('bfmeladder:'):
            references[reference] = reference.removeprefix('bfmeladder:')
        elif ':' not in reference:
            references[reference] = reference
        uuid = (row.calculation or {}).get('uuid')
        if uuid:
            historical_users[uuid] = row.user_id
    if not references:
        return []
    matches = db.query(Match).options(selectinload(Match.participants)).filter(Match.match_id.in_(references.values())).all()
    by_reference = {match.match_id: match for match in matches}
    unknown_results = {references[row.replay_id] for row in contributions
                       if row.replay_id in references and getattr(row, 'reason', None) == 'unknown_result'}
    recorded_by_id = {match.id: _recorded_players(match, match.match_id in unknown_results) for match in matches}
    identities = {p['uuid'] for recorded in recorded_by_id.values() for p in recorded if p['uuid']}
    linked = db.query(ExternalPlayerIdentity).filter(ExternalPlayerIdentity.source == 'bfmeladder', ExternalPlayerIdentity.external_uuid.in_(identities)).all() if identities else []
    user_ids = {identity.external_uuid: identity.user_id for identity in linked}
    user_ids.update(historical_users)
    users = {user.id: user for user in db.query(User).filter(User.id.in_(set(user_ids.values())))} if user_ids else {}
    storage = MapPreviewStorageService()
    result = []
    for replay_id, reference in references.items():
        match = by_reference.get(reference)
        if match is None:
            continue
        recorded = recorded_by_id[match.id]
        participants = []
        for item in recorded:
            user_id = user_ids.get(item['uuid']) if item['uuid'] else None
            user = users.get(user_id)
            participants.append(dict(user_id=user_id, name=(user.display_name or user.username) if user else item['name'],
                                     faction=item['faction'], team=item['team'], is_winner=item['is_winner'],
                                     avatar_url=user.avatar_url if user else None))
        result.append(dict(replay_id=replay_id, match_ref=reference, map_name=match.map_name,
                           map_preview_url=storage.public_url(match.map_name), game_mode=match.gamemode_name or match.game_mode,
                           patch_name=match.patch_name or match.patch_version, played_at=as_utc(match.match_date),
                           duration=match.duration, participants=participants))
    return result
