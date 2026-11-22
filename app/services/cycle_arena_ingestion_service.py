"""Создаёт ожидающие зачёта записи цикла по UUID из сохранённых ответов Арены.

Транзакцию фиксирует вызывающий код. Здесь нельзя подставлять текущий Elo профиля,
сопоставлять игроков по никам, подтверждать полноту загрузки или открывать заново
завершённый расчёт. Для зачёта адаптер исторического рейтинга должен предоставить
отдельное подтверждение рейтинга на момент игры.
"""

from collections import Counter
from datetime import timedelta
from uuid import UUID

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.cycle_battle import CycleMatchContribution, CycleTerritoryBattle
from app.models.cycle_interception import CycleInterception, CycleInterceptionContribution
from app.models.match import Match
from app.services.campaign_cycle_service import _utc
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.arena_replay_scan import ArenaReplayScan
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_interception_service import CycleInterceptionService
from app.services.cycle_match_service import CycleMatchService, ReplayFacts, ReplayPlayer
from app.services.cycle_reinforcement_store import CycleReinforcementStore
from app.services.elo_service import get_patch_family
from app.services.match_eligibility_service import RANKED_MODE_TEAM_SIZES


class CycleArenaIngestionService:
    @staticmethod
    def _report():
        return dict(cycles=0, scanned=0, territory_receipts=0, interception_receipts=0,
            pending_receipts=0, source_errors=0, protected_matches=0)

    @staticmethod
    def adapt(match):
        payload = match.source_payload if isinstance(match.source_payload, dict) else {}
        raw = payload.get('PublicApiPayload')
        if not isinstance(raw, dict) or raw.get('replayId') != match.match_id:
            raise ValueError('Original UUID-bound public replay response required')
        if raw.get('gameName') != 'RotWK':
            raise ValueError('RotWK public replay required')
        family = get_patch_family(raw.get('patchName'), raw.get('patchId'))
        if not family:
            raise ValueError('Supported source patch required')
        mode = ' '.join(str(raw.get('gamemode') or '').lower().split())
        size = RANKED_MODE_TEAM_SIZES.get(mode)
        source_players = raw.get('players')
        if not size or not isinstance(source_players, list):
            raise ValueError('Complete supported teams required')
        from app.services.arena_replay_rating_service import ArenaReplayRatingService
        historical_ratings = ArenaReplayRatingService.read(payload.get('ArenaReplayRatings'), raw)
        players, flags, rank_signal = [], {}, False
        for source in source_players:
            if not isinstance(source, dict) or type(source.get('isObserver', False)) is not bool:
                raise ValueError('Typed source player required')
            if source.get('isObserver', False):
                continue
            try:
                identity = str(UUID(source.get('uuid')))
            except (ValueError, TypeError, AttributeError) as error:
                raise ValueError('Permanent source player UUID required') from error
            team = source.get('team')
            if type(team) is not int:
                raise ValueError('Explicit source team required')
            if identity in flags:
                raise ValueError('Duplicate source player UUID')
            flag = source.get('isWinner')
            flags[identity] = flag if type(flag) is bool else None
            elo = historical_ratings.get(identity)
            players.append(ReplayPlayer(identity, team, elo, elo is not None, family if elo is not None else None))
            rank_signal |= any(type(source.get(key)) is int for key in ('oldRank', 'newRank'))
        teams = Counter(player.team for player in players)
        if len(teams) != 2 or set(teams.values()) != {size}:
            raise ValueError('Complete balanced source teams required')
        winners = {player.team for player in players if flags[player.uuid] is True}
        winner = next(iter(winners)) if len(winners) == 1 else None
        if winner is not None and any(flags[player.uuid] is not (player.team == winner) for player in players):
            winner = None
        result = ReplayFacts(match.match_id, 'bfmeladder', family,
            payload.get('IsValid') is True and rank_signal, None, None, tuple(players), winner)
        CycleMatchService._validate(result)
        return result.with_arena_times(date_ms=raw.get('date'), duration=raw.get('duration'))

    @staticmethod
    def _protected(rows):
        return any(row.counted or getattr(row, 'review_reason', None) is not None for row in rows)

    @staticmethod
    def _arena_rejected(match):
        payload = match.source_payload
        return (isinstance(payload, dict) and payload.get('Source') == 'bfme_arena_html'
                and 'PublicApiPayload' not in payload and payload.get('ReplayId') == match.match_id
                and payload.get('ArenaReplayRejection') == {
                    'source': 'bfmeladder_replay_html', 'replay_id': match.match_id, 'status': 'invalid',
                })

    @staticmethod
    def _source_status(db, cycle, match, *, valid):
        key = f'source-replay:{match.id}'
        if valid:
            if key in cycle.dependencies and not cycle.dependencies[key]:
                CampaignCycleStore().complete_dependency(db, cycle_id=cycle.id, key=key)
        elif cycle.dependencies.get(key) is not False or cycle.import_verified_at is not None:
            CampaignCycleStore._bump(db, cycle)
            cycle.dependencies = {**cycle.dependencies, key: False}
            cycle.import_verified_at = None
            # Неопознанные игроки могут участвовать в любом незавершённом перехвате цикла.
            for record in db.query(CycleInterception).filter_by(cycle_id=cycle.id, completed_at=None):
                record.verified_at = record.verified_revision = None
                record.source_cursor = record.covered_start = record.covered_end = None
            db.flush()

    @staticmethod
    def _matches(db, *, cycle, timeline, now, scan):
        end = min(now, timeline.battle_ends_at)
        matches = {row.id: row for row in db.query(Match).filter(
            Match.game_name == 'RotWK', Match.is_live.is_(False),
            Match.match_date >= timeline.battle_at, Match.match_date <= end)}
        unresolved_ids = sorted(int(key.partition(':')[2]) for key, done in cycle.dependencies.items()
            if key.startswith('source-replay:') and not done and key.partition(':')[2].isdigit())
        for offset in range(0, len(unresolved_ids), 250):
            matches.update({row.id: row for row in db.query(Match).filter(
                Match.id.in_(unresolved_ids[offset:offset + 250]))})
        pending = {'missing_historical_elo', 'missing_match_times', 'unknown_result', 'interception_pending'}
        receipts = db.query(CycleMatchContribution.replay_id).join(CycleTerritoryBattle).filter(
            CycleTerritoryBattle.cycle_id == cycle.id, CycleMatchContribution.review_reason.is_(None),
            CycleMatchContribution.reason.in_(pending)).all()
        receipts += db.query(CycleInterceptionContribution.replay_id).join(CycleInterception).filter(
            CycleInterception.cycle_id == cycle.id, CycleInterception.completed_at.is_(None),
            CycleInterceptionContribution.reason.in_(pending)).all()
        pending_ids = {key.removeprefix('bfmeladder:') for (key,) in receipts if key.startswith('bfmeladder:')}
        replay_ids = sorted(pending_ids | (scan.replay_ids if isinstance(scan, ArenaReplayScan) else frozenset()))
        if replay_ids:
            # Свежий ответ Арены важнее старой даты в локальной записи матча.
            for offset in range(0, len(replay_ids), 250):
                for match in db.query(Match).filter(Match.match_id.in_(replay_ids[offset:offset + 250]),
                        Match.game_name == 'RotWK', Match.is_live.is_(False)):
                    payload = match.source_payload if isinstance(match.source_payload, dict) else {}
                    raw = payload.get('PublicApiPayload')
                    start = ReplayFacts.arena_start(raw.get('date')) if isinstance(raw, dict) else None
                    if match.match_id in pending_ids or start is None or timeline.battle_at <= start <= end:
                        matches[match.id] = match
        return [matches[key] for key in sorted(matches)]

    def ingest_cycle(self, db, *, cycle_id, now, scan=None):
        now, report = _utc(now), self._report()
        with CycleEconomyStore._atomic(db):
            cycle = CampaignCycleStore()._locked(db, cycle_id)
            season = db.get(CampaignSeason, cycle.season_id)
            timeline = CampaignCycleStore.timeline(cycle)
            if (season.status != 'active' or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1'
                    or cycle.settled_at is not None or cycle.orders_frozen_at is None
                    or not cycle.battles_registered or now < timeline.battle_at):
                return report
            report['cycles'] = 1
            _, _, state, bindings = CycleReinforcementStore()._locked(db, cycle.id)
            known = {str(identity.uuid) for _, identity in bindings.values()}
            battles = db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle.id).order_by(
                CycleTerritoryBattle.id).all()
            targets = {battle.id: {str(bindings[uid][1].uuid) for side in battle.sides
                for uid in side['user_ids']} for battle in battles}
            for dispatch in state.dispatches:
                for battle in battles:
                    if battle.territory_id == dispatch.territory_id:
                        targets[battle.id].update(str(player.uuid) for player in dispatch.players)
            ambush_targets = {dispatch.id: {str(player.uuid) for player in dispatch.players} |
                {str(player.uuid) for ambush in state.ambushes if ambush.dispatch_id == dispatch.id
                 for player in ambush.players} for dispatch in state.dispatches}
            records = {record.dispatch_id: record for record in db.query(CycleInterception).filter_by(cycle_id=cycle.id)}
            matches = self._matches(db, cycle=cycle, timeline=timeline, now=now, scan=scan)
            for match in matches:
                report['scanned'] += 1
                if self._arena_rejected(match):
                    self._source_status(db, cycle, match, valid=True)
                    continue
                try:
                    replay = self.adapt(match)
                except ValueError:
                    report['source_errors'] += 1
                    self._source_status(db, cycle, match, valid=False)
                    continue
                source_start = ReplayFacts.arena_start(match.source_payload['PublicApiPayload'].get('date'))
                self._source_status(db, cycle, match, valid=source_start is not None)
                if source_start is None:
                    report['source_errors'] += 1
                player_ids = {player.uuid for player in replay.players}
                if not known.intersection(player_ids):
                    continue
                if replay.finished_at is not None and replay.finished_at > now:
                    continue
                replay_id = f'bfmeladder:{replay.replay_id}'
                candidate_start = source_start or as_utc(match.match_date)
                # У перехватов отдельный зачёт; используется исходное время движения помощи.
                for dispatch in state.dispatches:
                    record = records.get(dispatch.id)
                    existing = db.query(CycleInterceptionContribution).filter_by(
                        interception_id=record.id, replay_id=replay_id).all() if record else []
                    if (not dispatch.ambush_clan_ids or now < dispatch.interception_at
                            or not ambush_targets[dispatch.id].intersection(player_ids)
                            or not existing and not dispatch.interception_at <= candidate_start < dispatch.interception_ends_at):
                        continue
                    if (record is not None and record.completed_at is not None) or self._protected(existing):
                        report['protected_matches'] += 1
                        continue
                    rows = CycleInterceptionService().process(db, cycle_id=cycle.id,
                        dispatch_id=dispatch.id, replay=replay)
                    report['interception_receipts'] += len(rows)
                    report['pending_receipts'] += sum(row.reason in {'missing_historical_elo',
                        'missing_match_times', 'unknown_result'} for row in rows)
                    if rows and record is None:
                        records[dispatch.id] = db.get(CycleInterception, rows[0].interception_id)
                for battle in battles:
                    if not targets[battle.id].intersection(player_ids):
                        continue
                    existing = db.query(CycleMatchContribution).filter_by(battle_id=battle.id, replay_id=replay_id).all()
                    if battle.completed_at is not None or self._protected(existing):
                        report['protected_matches'] += 1
                        continue
                    rows = CycleMatchService().process(db, battle_id=battle.id, replay=replay)
                    report['territory_receipts'] += len(rows)
                    report['pending_receipts'] += sum(row.reason in {'missing_historical_elo',
                        'missing_match_times', 'unknown_result', 'interception_pending'} for row in rows)
            return report

    def ingest_pending(self, db, *, now):
        report = self._report()
        cycles = db.query(CampaignCycleRecord.id).join(CampaignSeason).filter(
            CampaignSeason.status == 'active', CampaignCycleRecord.settled_at.is_(None),
            CampaignCycleRecord.orders_frozen_at.isnot(None)).order_by(CampaignCycleRecord.id).all()
        for (cycle_id,) in cycles:
            result = self.ingest_cycle(db, cycle_id=cycle_id, now=now)
            for key in report:
                report[key] += result[key]
        return report

    def verify_pending(self, db, *, scan, now):
        """Подтверждает окна только по полному сохранённому обходу, включая догрузку.

        Сначала завершаются готовые перехваты, затем повторяется территориальный
        зачёт их участников. Неполные данные не превращаются в битву без матчей.
        """
        now = _utc(now)
        report = dict(cycles_verified=0, interceptions_verified=0, interceptions_settled=0)
        if not isinstance(scan, ArenaReplayScan):
            return report
        with CycleEconomyStore._atomic(db):
            cycles = db.query(CampaignCycleRecord).join(CampaignSeason).filter(
                CampaignSeason.status == 'active', CampaignCycleRecord.settled_at.is_(None),
                CampaignCycleRecord.orders_frozen_at.isnot(None)).order_by(CampaignCycleRecord.id).all()
            for candidate in cycles:
                cycle = CampaignCycleStore()._locked(db, candidate.id)
                season = db.get(CampaignSeason, cycle.season_id)
                if ((season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1'
                        or not cycle.battles_registered or cycle.settled_at is not None):
                    continue
                self.ingest_cycle(db, cycle_id=cycle.id, now=now, scan=scan)
                if any(not done for key, done in cycle.dependencies.items() if key.startswith('source-replay:')):
                    continue
                _, _, state, _ = CycleReinforcementStore()._locked(db, cycle.id)
                records = {r.dispatch_id: r for r in db.query(CycleInterception).filter_by(cycle_id=cycle.id)}
                for dispatch in state.dispatches:
                    record = records.get(dispatch.id)
                    if (not dispatch.ambush_clan_ids or record is not None and record.completed_at is not None
                            or not scan.covers(start=dispatch.interception_at,
                                deadline=dispatch.interception_ends_at + timedelta(minutes=5), now=now)):
                        continue
                    if (record is not None and record.verified_at is not None
                            and record.verified_revision == record.revision and record.source_cursor == scan.source_cursor):
                        continue
                    CycleInterceptionService()._verify_window(db, cycle_id=cycle.id, dispatch_id=dispatch.id,
                        covered_start=scan.covered_start, covered_end=scan.covered_end,
                        source_cursor=scan.source_cursor, now=now)
                    report['interceptions_verified'] += 1
                settled = CycleInterceptionService().settle_ready(db, cycle_id=cycle.id, now=now)
                report['interceptions_settled'] += len(settled)
                if settled:
                    self.ingest_cycle(db, cycle_id=cycle.id, now=now, scan=scan)
                timeline = CampaignCycleStore.timeline(cycle)
                if not scan.covers(start=timeline.battle_at, deadline=timeline.replay_deadline, now=now):
                    continue
                pending = db.query(CycleMatchContribution.id).join(CycleTerritoryBattle).filter(
                    CycleTerritoryBattle.cycle_id == cycle.id, CycleMatchContribution.review_reason.is_(None),
                    CycleMatchContribution.reason.in_(('missing_historical_elo', 'missing_match_times',
                        'unknown_result', 'interception_pending'))).first()
                if pending is None and cycle.import_verified_at is None:
                    CampaignCycleStore().mark_import_complete(db, cycle_id=cycle.id, verified_at=now)
                    report['cycles_verified'] += 1
            return report
