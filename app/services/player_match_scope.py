"""Match ownership follows Arena UUID, with aliases for legacy imports."""
from sqlalchemy import and_, func, or_

from app.models.match import Match, MatchParticipant
from app.services.external_identity_service import ExternalIdentityService


class PlayerMatchScope:
    def __init__(self, db, user, requested_name=''):
        self.user = user
        names = ExternalIdentityService().names_for_user(db, user.id) if user else {requested_name}
        self.names = {name.strip().lower() for name in names if name and name.strip()}
        self.uuids = {identity.external_uuid for identity in (user.external_identities if user else [])}

    @classmethod
    def resolve(cls, db, requested_name):
        from app.services.user_service import UserService
        return cls(db, UserService().get_public_profile(db, requested_name), requested_name)

    def _predicate(self, name, uuid):
        return or_(uuid.in_(self.uuids), and_(
            or_(uuid.is_(None), uuid == ""), func.lower(func.trim(name)).in_(self.names),
        ))

    def query(self, db):
        query = db.query(Match).filter(or_(
            and_(~Match.participants.any(), or_(
                self._predicate(Match.winner_player, Match.winner_player_uuid),
                self._predicate(Match.loser_player, Match.loser_player_uuid),
            )),
            Match.participants.any(and_(
                self._predicate(MatchParticipant.nickname, MatchParticipant.player_uuid),
                MatchParticipant.is_observer.is_(False),
            )),
        ))
        if self.user and self.user.statistics_started_at is not None:
            query = query.filter(Match.match_date >= self.user.statistics_started_at)
        return query

    def owns(self, name, uuid):
        if uuid:
            return uuid in self.uuids
        return str(name or "").strip().lower() in self.names

    def participant(self, match):
        return next((p for p in match.participants if not p.is_observer and self.owns(p.nickname, p.player_uuid)), None)

    def is_winner(self, match):
        participant = self.participant(match)
        if participant is not None:
            return bool(participant.is_winner)
        return self.owns(match.winner_player, match.winner_player_uuid)
