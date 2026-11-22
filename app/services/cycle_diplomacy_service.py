"""Independent cycle_v1 persistence; no commits, rollbacks, legacy writes or I/O.

Call mutations inside a caller-owned transaction, rolling it back on database or
concurrency errors. Season-row serialization covers first pair creation and
different cycles; cycle revision CAS additionally follows the cycle store contract.
SQLite tests cannot prove PostgreSQL row-lock behavior.

Use the latest persisted cycle, not a guessed wall-clock cycle. Settlement advances
the relationship cursor immediately (including rest). A proposal lasts through
settlement of its second full cycle. No expiry jobs or calendar timers are needed.
The internal reveal method expects an already validated attack; callers must not
expose it as a user command or invoke it for hidden planning/ownerless territory.
"""

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.clan import Clan
from app.models.cycle_diplomacy import CycleDiplomacyEvent, CycleDiplomacyPair, CycleDiplomacyProposal
from app.services.campaign_cycle_service import CyclePhase, _utc
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict


def _positive(value):
    if type(value) is not int or value < 1:
        raise ValueError('Positive integer required')
    return value


def first_full_cycle(number, phase):
    """Prep includes the upcoming battle; rest/partial battle skip current cycle.

    Registration is included for completeness of the pure timing calculation,
    but the mutation gate does not permit diplomacy during registration.
    """
    _positive(number)
    phase = CyclePhase(phase)
    if phase == CyclePhase.SEASON_ENDED:
        raise ValueError('Season has ended')
    return number if phase in (CyclePhase.REGISTRATION, CyclePhase.PREPARATION) else number + 1


def _cursor(cycle, now):
    CampaignCycleStore.timeline(cycle).phase_at(now)
    settled = cycle.settled_at is not None and _utc(now) >= as_utc(cycle.settled_at)
    return cycle.number + int(settled)


def _active(pair, cursor):
    return {key: value for key, value in (pair.declarations if pair else {}).items()
            if value['last_cycle'] is None or int(value['last_cycle']) >= cursor}


class CycleDiplomacyService:
    def _context(self, db, cycle_id, now, *, manual):
        _positive(cycle_id)
        now = _utc(now)
        cycle = CampaignCycleStore()._locked(db, cycle_id)
        season = db.query(CampaignSeason).filter_by(id=cycle.season_id).with_for_update().populate_existing().one()
        if (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
            raise ValueError('Season must explicitly enable cycle_v1')
        if season.status != 'active':
            raise ValueError('Active season required')
        if db.query(CampaignCycleRecord.id).filter(
            CampaignCycleRecord.season_id == cycle.season_id,
            CampaignCycleRecord.number > cycle.number,
        ).first():
            raise ValueError('Latest cycle required')
        phase = CampaignCycleStore.timeline(cycle).phase_at(now)
        if manual and phase not in (CyclePhase.PREPARATION, CyclePhase.REST):
            raise ValueError('Diplomacy requires preparation or rest')
        if not manual and phase not in (CyclePhase.BATTLE, CyclePhase.REPLAY_LOADING, CyclePhase.SETTLEMENT):
            raise ValueError('Attack hostility requires battle reveal')
        return cycle, phase, now

    def _pair(self, db, cycle, clan_id, other_clan_id, actor_user_id=None, expected_revision=None):
        _positive(clan_id)
        _positive(other_clan_id)
        if clan_id == other_clan_id:
            raise ValueError('Distinct clans required')
        clans = db.query(Clan).filter(Clan.id.in_((clan_id, other_clan_id))).order_by(Clan.id).with_for_update().populate_existing().all()
        if len(clans) != 2 or any(c.is_deleted for c in clans):
            raise ValueError('Two existing nondeleted clans required')
        if actor_user_id is not None:
            _positive(actor_user_id)
            if next(c for c in clans if c.id == clan_id).leader_id != actor_user_id:
                raise PermissionError('Only the current head controls diplomacy')
        pair = db.query(CycleDiplomacyPair).filter_by(
            season_id=cycle.season_id, clan_low_id=clans[0].id, clan_high_id=clans[1].id,
        ).with_for_update().populate_existing().one_or_none()
        if expected_revision is not None:
            if type(expected_revision) is not int or expected_revision < 0:
                raise ValueError('Nonnegative revision required')
            if expected_revision != (pair.revision if pair else 0):
                raise CycleConflict('Diplomacy revision changed; refresh before retry')
        return pair

    @staticmethod
    def _write(db, cycle, pair, clan_id, other_clan_id, actor_user_id, kind, now, payload=None, resolved=None):
        CampaignCycleStore._bump(db, cycle)
        if pair is None:
            pair = CycleDiplomacyPair(season_id=cycle.season_id,
                clan_low_id=min(clan_id, other_clan_id), clan_high_id=max(clan_id, other_clan_id),
                revision=1, declarations={})
            db.add(pair)
            db.flush()
        else:
            pair.revision += 1
        event = CycleDiplomacyEvent(pair_id=pair.id, cycle_id=cycle.id, actor_clan_id=clan_id,
            actor_user_id=actor_user_id, kind=kind, occurred_at=now, payload=payload or {},
            resolved_proposal_id=resolved)
        db.add(event)
        return pair, event

    def _manual(self, db, cycle_id, clan_id, other_clan_id, actor_user_id, now, expected_revision):
        _positive(actor_user_id)
        cycle, phase, now = self._context(db, cycle_id, now, manual=True)
        pair = self._pair(db, cycle, clan_id, other_clan_id, actor_user_id, expected_revision)
        return cycle, phase, now, pair

    def declare_war(self, db, *, cycle_id, clan_id, other_clan_id, actor_user_id, duration, now,
                    expected_revision=None):
        if duration is not None:
            _positive(duration)
        cycle, phase, now, pair = self._manual(db, cycle_id, clan_id, other_clan_id, actor_user_id, now, expected_revision)
        if pair and pair.allied_at is not None:
            raise ValueError('Break alliance before declaring war')
        first = first_full_cycle(cycle.number, phase)
        term = dict(first_cycle=first, last_cycle=str(first + duration - 1) if duration is not None else None,
                    source='declaration', declared_at=now.isoformat())
        pair, _ = self._write(db, cycle, pair, clan_id, other_clan_id, actor_user_id, 'war_declared', now, term)
        pair.declarations = {**pair.declarations, str(clan_id): term}
        db.flush()
        return pair

    def record_revealed_attack(self, db, *, cycle_id, attacker_clan_id, defender_clan_id, now):
        cycle, _, now = self._context(db, cycle_id, now, manual=False)
        pair = self._pair(db, cycle, attacker_clan_id, defender_clan_id)
        if pair and pair.allied_at is not None:
            raise ValueError('Cannot attack an ally')
        current = _active(pair, cycle.number).get(str(attacker_clan_id))
        term = dict(first_cycle=cycle.number, last_cycle=str(cycle.number), source='attack', declared_at=now.isoformat())
        pair, _ = self._write(db, cycle, pair, attacker_clan_id, defender_clan_id, None,
                              'attack_revealed', now, {'term': term, 'preserved_existing': current is not None})
        if current is None:
            pair.declarations = {**pair.declarations, str(attacker_clan_id): term}
        db.flush()
        return pair

    def offer(self, db, *, cycle_id, clan_id, other_clan_id, actor_user_id, kind, now, expected_revision=None):
        if kind not in ('peace', 'alliance'):
            raise ValueError('Unknown proposal kind')
        cycle, phase, now, pair = self._manual(db, cycle_id, clan_id, other_clan_id, actor_user_id, now, expected_revision)
        hostile = bool(_active(pair, _cursor(cycle, now)))
        if kind == 'alliance' and (hostile or (pair and pair.allied_at is not None)):
            raise ValueError('Alliance requires nonhostile, nonallied clans')
        if kind == 'peace' and not hostile:
            raise ValueError('Peace requires hostility')
        first = first_full_cycle(cycle.number, phase)
        pair, event = self._write(db, cycle, pair, clan_id, other_clan_id, actor_user_id, 'proposal_offered', now)
        proposal = CycleDiplomacyProposal(pair_id=pair.id, sender_clan_id=clan_id, kind=kind,
            created_at=now, first_full_cycle=first, expires_after_cycle=first + 1)
        db.add(proposal)
        db.flush()
        event.payload = {'proposal_id': proposal.id, 'kind': kind}
        db.flush()
        return proposal

    def proposal_status(self, db, proposal, *, cycle, now):
        """Internal projection only; not an authorization boundary or public API."""
        pair = db.get(CycleDiplomacyPair, proposal.pair_id)
        if pair.season_id != cycle.season_id:
            raise ValueError('Proposal season mismatch')
        event = db.query(CycleDiplomacyEvent).filter_by(resolved_proposal_id=proposal.id).one_or_none()
        if event:
            return 'accepted' if event.kind == 'proposal_accepted' else 'revoked'
        return 'expired' if _cursor(cycle, now) > proposal.expires_after_cycle else 'pending'

    def _resolve(self, db, *, cycle_id, clan_id, other_clan_id, actor_user_id, proposal_id, now,
                 expected_revision=None, accept):
        _positive(proposal_id)
        cycle, _, now, pair = self._manual(db, cycle_id, clan_id, other_clan_id, actor_user_id, now, expected_revision)
        proposal = db.get(CycleDiplomacyProposal, proposal_id)
        if pair is None or proposal is None or proposal.pair_id != pair.id:
            raise ValueError('Unknown proposal for this season/pair')
        if self.proposal_status(db, proposal, cycle=cycle, now=now) != 'pending':
            raise ValueError('Proposal is no longer pending')
        if now < as_utc(proposal.created_at):
            raise ValueError('Proposal has not been created yet')
        if (proposal.sender_clan_id == clan_id) == accept:
            raise ValueError('Only recipient accepts; only sender revokes')
        if accept and proposal.kind == 'alliance' and (_active(pair, _cursor(cycle, now)) or pair.allied_at is not None):
            raise ValueError('Alliance requires nonhostile, nonallied clans')
        pair, _ = self._write(db, cycle, pair, clan_id, other_clan_id, actor_user_id,
            'proposal_accepted' if accept else 'proposal_revoked', now,
            {'kind': proposal.kind}, resolved=proposal.id)
        if accept:
            if proposal.kind == 'peace':
                pair.declarations = {}
            else:
                pair.allied_at = now
        db.flush()
        return pair

    def accept(self, db, **kwargs):
        return self._resolve(db, accept=True, **kwargs)

    def revoke(self, db, **kwargs):
        return self._resolve(db, accept=False, **kwargs)

    def break_alliance(self, db, *, cycle_id, clan_id, other_clan_id, actor_user_id, now, expected_revision=None):
        cycle, _, now, pair = self._manual(db, cycle_id, clan_id, other_clan_id, actor_user_id, now, expected_revision)
        if pair is None or pair.allied_at is None:
            raise ValueError('No alliance to break')
        pair, _ = self._write(db, cycle, pair, clan_id, other_clan_id, actor_user_id, 'alliance_broken', now)
        pair.allied_at = None
        db.flush()
        return pair

    def public_projection(self, db, *, season_id, now):
        _positive(season_id)
        now = _utc(now)
        season = db.get(CampaignSeason, season_id)
        if season is None or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
            raise ValueError('Season must explicitly enable cycle_v1')
        cycle = db.query(CampaignCycleRecord).filter_by(season_id=season_id).order_by(CampaignCycleRecord.number.desc()).first()
        if cycle is None:
            return []
        cursor = _cursor(cycle, now)
        result = []
        # Neither proposal-only rows nor proposal-driven revisions are public.
        public_pairs = db.query(CycleDiplomacyEvent.pair_id).filter(
            CycleDiplomacyEvent.kind.in_(('war_declared', 'attack_revealed',
                                          'alliance_broken', 'proposal_accepted')),
        )
        for pair in db.query(CycleDiplomacyPair).filter(
            CycleDiplomacyPair.season_id == season_id,
            CycleDiplomacyPair.id.in_(public_pairs),
        ).order_by(
            CycleDiplomacyPair.clan_low_id, CycleDiplomacyPair.clan_high_id,
        ).all():
            terms = {key: {**term, 'remaining_cycles': None if term['last_cycle'] is None else
                          int(term['last_cycle']) - cursor + 1} for key, term in _active(pair, cursor).items()}
            result.append(dict(clan_low_id=pair.clan_low_id, clan_high_id=pair.clan_high_id,
                status='hostile' if terms else 'allied' if pair.allied_at else 'neutral',
                allied_at=pair.allied_at, declarations=terms))
        return result
