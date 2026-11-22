"""Обезличенные примеры реплеев в изолированной игровой ситуации, без сети."""

import importlib.util
import json
import os
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = json.loads((ROOT / 'tests/fixtures/arena_replay_ratings_20261024.json').read_text(encoding='utf-8'))['samples']


def runner():
    path = ROOT / 'scripts/rehearse_cycle_replays.py'
    spec = importlib.util.spec_from_file_location('replay_acceptance', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def acceptance_db(db, tmp_path):
    source = os.environ.get('ARENA_ACCEPTANCE_DATABASE')
    if not source:
        yield db
        return
    path = Path(source).resolve()
    runner().validate_copy(path, root=ROOT)
    target = tmp_path / 'replay-acceptance.db'
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as original:
        with sqlite3.connect(target) as copied:
            original.backup(copied)
    engine = create_engine('sqlite:///' + target.as_posix())
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('sample_index,kind', [(0, 'territory'), (1, 'territory'), (0, 'interception')])
async def test_real_replay_loader_uuid_scoring_settlement_and_income(acceptance_db, sample_index, kind):
    result = await runner().run_case(acceptance_db, SAMPLES[sample_index], kind=kind)
    assert result['source_ratings'] == SAMPLES[sample_index]['expected_ratings']
    assert result['old_current_rating_used'] is False
    assert result['duplicate_points'] is False
    assert result['settled'] is True
    assert result['income_credited'] is True
    assert result['coverage'] == 'isolated_fixture_not_live_history'
    directory = os.environ.get('ARENA_ACCEPTANCE_REPORT_DIR')
    if directory:
        target = Path(directory).resolve()
        assert target.is_relative_to((ROOT / '.tmp').resolve())
        target.mkdir(parents=True, exist_ok=True)
        (target / f'{sample_index}-{kind}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def test_all_captured_sources_remain_uuid_bound_including_patch_202():
    from app.services.arena_replay_rating_service import ArenaReplayRatingService as Ratings
    for sample in SAMPLES:
        assert Ratings.read(Ratings.parse(sample['html'], sample['raw']), sample['raw']) == sample['expected_ratings']


@pytest.mark.asyncio
async def test_acceptance_keeps_preexisting_identity_instead_of_reusing_test_uuid(db):
    from app.models.user import User
    from app.models.external_identity import ExternalPlayerIdentity
    from uuid import UUID
    user = User(username='Существующий пользователь', hashed_password='unused')
    db.add(user)
    db.flush()
    identity = ExternalPlayerIdentity(user_id=user.id, source='bfmeladder', external_uuid=str(UUID(int=1)),
        current_nickname=user.username, verification_status='verified')
    db.add(identity)
    db.commit()
    await runner().run_case(db, SAMPLES[0], kind='territory')
    db.refresh(identity)
    assert identity.user_id == user.id and identity.external_uuid == str(UUID(int=1))


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['swapped_elo', 'extra_contribution'])
async def test_acceptance_detects_wrong_uuid_ratings_and_duplicate_rows(db, monkeypatch, fault):
    from dataclasses import replace
    from app.services.cycle_arena_ingestion_service import CycleArenaIngestionService as Ingestion
    if fault == 'swapped_elo':
        original = Ingestion.adapt

        def corrupt(match):
            facts = original(match)
            return replace(facts, players=tuple(replace(player, elo=other.elo)
                for player, other in zip(facts.players, reversed(facts.players))))

        monkeypatch.setattr(Ingestion, 'adapt', staticmethod(corrupt))
    else:
        from app.models.cycle_battle import CycleMatchContribution
        from app.models.user import User
        original = Ingestion.verify_pending

        def corrupt(self, session, **kwargs):
            result = original(self, session, **kwargs)
            rows = session.query(CycleMatchContribution).all()
            source = rows[0]
            unused = session.query(User).filter(User.id.notin_([r.user_id for r in rows])).first()
            session.add(CycleMatchContribution(battle_id=source.battle_id, replay_id=source.replay_id,
                user_id=unused.id, clan_id=source.clan_id, points=source.points,
                counted=True, reason=source.reason, calculation=source.calculation))
            session.flush()
            return result

        monkeypatch.setattr(Ingestion, 'verify_pending', corrupt)
    with pytest.raises(AssertionError):
        await runner().run_case(db, SAMPLES[0], kind='territory')


@pytest.mark.parametrize('invalid', ['outside', 'missing_report', 'wrong_copy', 'not_readonly'])
def test_acceptance_refuses_unverified_or_working_database(tmp_path, invalid):
    path = tmp_path / ('.tmp/case/rehearsal.db' if invalid != 'outside' else 'working.db')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    if invalid != 'missing_report':
        report = {'copy': str(path if invalid != 'wrong_copy' else path.parent / 'other.db'),
                  'source_opened_read_only': invalid != 'not_readonly'}
        (path.parent / 'report.json').write_text(json.dumps(report), encoding='utf-8')
    with pytest.raises(ValueError):
        runner().validate_copy(path, root=tmp_path)
