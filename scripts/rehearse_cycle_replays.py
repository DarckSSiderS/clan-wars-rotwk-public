"""Инструмент тестовой приёмки: сохранённые реальные реплеи, только копия базы.

Запускается через tests/test_cycle_replay_acceptance.py. Игровые ситуации
изолированы; ответы тестового источника не подтверждают полноту живой Арены.
"""

from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import NAMESPACE_URL, uuid5


def validate_copy(path, *, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    manifest = path.parent / 'report.json'
    if (not path.is_relative_to(root / '.tmp') or path.name != 'rehearsal.db'
            or not path.is_file() or not manifest.is_file()):
        raise ValueError('Разрешена только проверенная копия rehearsal.db внутри .tmp')
    try:
        report = json.loads(manifest.read_text(encoding='utf-8'))
    except (ValueError, OSError) as error:
        raise ValueError('Нужен читаемый отчёт репетиции') from error
    if report.get('copy') != str(path) or report.get('source_opened_read_only') is not True:
        raise ValueError('Копия не подтверждена отчётом репетиции')


async def run_case(db, sample, *, kind):
    from app.config import settings
    from app.core.time import as_utc
    from app.models.campaign import CampaignSeason
    from app.models.campaign_cycle import CampaignCyclePlan
    from app.models.cycle_battle import CycleMatchContribution, CycleTerritoryBattle
    from app.models.cycle_interception import CycleInterceptionContribution
    from app.models.cycle_income import CycleTerritoryProfile
    from app.models.external_identity import ExternalPlayerIdentity
    from app.models.match import Match
    from app.models.territory import Territory, TerritoryOwnershipHistory
    from app.services.arena_replay_rating_service import ArenaReplayRatingService as Ratings
    from app.services.campaign_cycle_store import CampaignCycleStore
    from app.services.campaign_rule_service import CampaignRuleService
    from app.services.cycle_arena_ingestion_service import CycleArenaIngestionService
    from app.services.cycle_economy import Resources
    from app.services.cycle_economy_store import CycleEconomyStore
    from app.services.cycle_income_catalog import prepare_income_profiles, INCOME_CATALOG_VERSION
    from app.services.cycle_income_service import CycleIncomeService
    from app.services.cycle_match_service import ReplayFacts
    from app.services.cycle_reinforcement_store import CycleReinforcementStore
    from app.services.cycle_settlement_service import CycleSettlementService
    from app.services.ladder_service import BFMELadderService
    import app.services.ladder_service as ladder
    import tests.test_cycle_reinforcement_store as fixtures

    raw = deepcopy(sample['raw'])
    rating = Ratings.parse(sample['html'], raw)
    assert Ratings.read(rating, raw) == sample['expected_ratings']
    if kind not in {'territory', 'interception'} or raw['patchName'].startswith('Patch 2.02'):
        raise ValueError('Для нового зачёта нужен пример Ennorath и известный тип проверки')
    if db.query(CampaignSeason).filter_by(status='active').first():
        raise ValueError('Приёмка не останавливает существующий активный сезон')
    battle_at = ReplayFacts.arena_start(raw['date']) - timedelta(hours=3)
    rule = CampaignRuleService().get_active(db)
    with (patch.object(fixtures, 'T', battle_at),
          patch.object(fixtures, 'UUID', side_effect=lambda **kw: uuid5(NAMESPACE_URL, f'local-replay-acceptance:{kw["int"]}'))):
        users, clans, land, cycle = fixtures.world.__wrapped__(db)
    season = db.get(CampaignSeason, cycle.season_id)
    cycle.rule_version = rule.version
    season.rules_snapshot = {**season.rules_snapshot, 'version': rule.version}
    for clan in clans:
        clan.created_at = season.starts_at
    battle = db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle.id).one()
    existing_land = db.query(Territory).filter_by(name='Арнор', owner_clan_id=None).one_or_none()
    if existing_land:
        old_id = land.id
        existing_land.owner_clan_id = clans[1].id
        cycle.planning_snapshot = [{'id': existing_land.id, 'owner_clan_id': clans[1].id}]
        battle.territory_id = existing_land.id
        for plan in db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id):
            plan.orders = [{**o, 'territory_id': existing_land.id if o['territory_id'] == old_id else o['territory_id']}
                           for o in plan.orders]
        db.delete(land)
        land = existing_land
    winners = [p for p in raw['players'] if p['isWinner']]
    losers = [p for p in raw['players'] if not p['isWinner']]
    assert len(winners) == len(losers) <= 2
    assignments = list(zip((5, 6), winners)) + list(zip((3, 4), losers)) if kind == 'territory' else [(1, winners[0]), (6, losers[0])]
    for index, player in assignments:
        identity = db.query(ExternalPlayerIdentity).filter_by(user_id=users[index].id).one()
        identity.external_uuid = player['uuid']
    if kind == 'territory':
        for clan, indexes, order_kind in [(clans[1], (3, 4)[:len(losers)], 'defend'), (clans[2], (5, 6)[:len(winners)], 'attack')]:
            plan = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id, clan_id=clan.id).one()
            plan.orders = [dict(user_id=users[i].id, kind=order_kind, territory_id=land.id) for i in indexes]
        battle.sides = [dict(clan_id=clans[1].id, user_ids=[users[i].id for i in (3, 4)[:len(losers)]]),
                        dict(clan_id=clans[2].id, user_ids=[users[i].id for i in (5, 6)[:len(winners)]])]
    db.flush()
    copied_map = db.query(Territory).count() > 1
    if copied_map:
        island = db.query(Territory).filter_by(name='Тол-Фалас').one()
        island.is_playable = island.has_port = False
        db.flush()
        prepare_income_profiles(db, season_id=season.id, catalog_version=INCOME_CATALOG_VERSION,
            now=as_utc(season.starts_at), apply=True)
    else:
        CycleIncomeService().configure_profile(db, season_id=season.id, territory_id=land.id,
            base=Resources(100, iron=4), profile_material='iron', now=as_utc(season.starts_at))
    db.add(TerritoryOwnershipHistory(territory_id=land.id, clan_id=clans[1].id, started_at=season.starts_at))
    wallets = [CycleEconomyStore().ensure_state(db, season_id=season.id, clan_id=c.id) for c in clans]
    for wallet in wallets:
        CycleEconomyStore().freeze_snapshot(db, state_id=wallet.id, cycle_id=cycle.id,
            now=battle_at, expected_revision=wallet.revision)
    store = CycleReinforcementStore()
    store.initialize(db, cycle_id=cycle.id)
    if kind == 'interception':
        store.request_help(db, cycle_id=cycle.id, request_id='real:q', clan_id=clans[1].id,
            territory_id=land.id, actor_user_id=users[3].id, now=battle_at)
        store.dispatch(db, cycle_id=cycle.id, dispatch_id='real:d', sender_clan_id=clans[0].id,
            recipient_clan_id=clans[1].id, territory_id=land.id, player_user_ids=[users[1].id],
            actor_user_id=users[0].id, request_id='real:q', now=battle_at)
    db.commit()

    class Response:
        status = 200

        def __init__(self, payload=None):
            self.payload = payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def json(self):
            return deepcopy(self.payload)

        async def text(self):
            return sample['html']

    class Source(Response):
        def get(self, url, *, params=None, headers=None, **kwargs):
            if params is not None:
                assert url == settings.LADDER_PUBLIC_API_BASE
                selected = params['arena'] == raw['arenaId'] and params['gamemode'] == raw['gamemode']
                return Response([raw] if selected else [])
            assert url.rstrip('/').endswith('/' + raw['replayId'])
            assert 'Authorization' not in (headers or {})
            return Response()

    importer = CycleArenaIngestionService()
    with (patch.object(settings, 'LADDER_PUBLIC_API_ENABLED', True),
          patch.object(settings, 'LADDER_PUBLIC_API_TOKEN', 'isolated-fixture-not-a-live-token'),
          patch.object(settings, 'PROXY_URL', ''),
          patch.object(ladder.aiohttp, 'TCPConnector', return_value=None),
          patch.object(ladder.aiohttp, 'ClientSession', return_value=Source()),
          patch.object(BFMELadderService, '_capture_team_ratings', new=AsyncMock(return_value=None)),
          patch.object(ladder.ReplayStorageService, 'download_match', new=AsyncMock()),
          patch.object(ladder.MapPreviewStorageService, 'download_match', new=AsyncMock()),
          patch.object(ladder.asyncio, 'sleep', new=AsyncMock())):
        loader = BFMELadderService()
        now = ReplayFacts.arena_start(raw['date']) + timedelta(hours=1)
        await loader.fetch_and_save_matches_from_api(db, start_override_ms=int(battle_at.timestamp() * 1000),
            end_override_ms=int(now.timestamp() * 1000))
        match = db.query(Match).filter_by(match_id=raw['replayId']).one()
        assert Ratings.read(match.source_payload['ArenaReplayRatings'], raw) == sample['expected_ratings']
        users[assignments[0][0]].username = 'Имя изменено после загрузки'
        importer.ingest_cycle(db, cycle_id=cycle.id, now=now)
        model = CycleMatchContribution if kind == 'territory' else CycleInterceptionContribution
        bindings = {users[index].id: player for index, player in assignments}
        teams = {p['team'] for p in raw['players']}
        averages = {team: sum(Decimal(sample['expected_ratings'][p['uuid']]) for p in raw['players']
                    if p['team'] == team) / sum(p['team'] == team for p in raw['players']) for team in teams}

        def read_contributions():
            rows = db.query(model).filter_by(replay_id='bfmeladder:' + raw['replayId']).populate_existing().order_by(model.user_id).all()
            assert len(rows) == len(bindings) and {r.user_id for r in rows} == set(bindings)
            actual = {bindings[r.user_id]['uuid']: int(Decimal(r.calculation['historical_elo'])) for r in rows}
            assert actual == sample['expected_ratings'] and all(r.counted for r in rows)
            for row in rows:
                player = bindings[row.user_id]
                opponent = next(team for team in teams if team != player['team'])
                difference = max(Decimal(-400), min(Decimal(400), averages[opponent] - averages[player['team']]))
                expected = (Decimal(100) + difference / 8 if player['isWinner'] else Decimal(-50) + difference / 16) * 2
                assert row.points == expected
            return rows, actual, [(r.id, r.user_id, str(r.points), r.counted) for r in rows]

        rows, actual_ratings, before = read_contributions()
        deadline = CampaignCycleStore.timeline(cycle).replay_deadline
        await loader.fetch_and_save_matches_from_api(db, start_override_ms=int(battle_at.timestamp() * 1000),
            end_override_ms=int(deadline.timestamp() * 1000))
        importer.verify_pending(db, scan=loader.last_completed_scan, now=deadline)
        rows, actual_ratings, after = read_contributions()
        assert after == before
        CycleSettlementService().settle(db, cycle_id=cycle.id, now=deadline)
        assert land.owner_clan_id == (clans[2].id if kind == 'territory' else clans[1].id)
        wallet_before = [dict(w.wallet) for w in wallets]
        CycleSettlementService().settle(db, cycle_id=cycle.id, now=deadline)
        assert [w.wallet for w in wallets] == wallet_before
        gains = [CycleIncomeService().accrue(db, state_id=w.id, now=deadline + timedelta(days=1)) for w in wallets]
        assert all(g.gold > 0 for g in gains)
        profile = db.query(CycleTerritoryProfile).filter_by(season_id=season.id, territory_id=land.id).one()
        base = Resources(**profile.base)
        owner = 2 if kind == 'territory' else 1
        for material in ('gold', 'iron', 'wood', 'food', 'mithril'):
            assert getattr(gains[owner], material) == getattr(gains[0], material) + getattr(base, material)
        db.commit()
        return dict(replay_id=raw['replayId'], kind=kind, source_ratings=actual_ratings,
            old_current_rating_used=False, duplicate_points=False, settled=cycle.settled_at is not None,
            income_credited=True, coverage='isolated_fixture_not_live_history', copied_map=copied_map,
            territory=land.name, winner_clan_id=battle.winner_clan_id,
            daily_income=[{key: str(getattr(gain, key)) for key in ('gold', 'iron', 'wood', 'food', 'mithril')} for gain in gains],
            contributions=[dict(user_id=r.user_id, points=str(r.points), elo=r.calculation['historical_elo']) for r in rows])
