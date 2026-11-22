from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.v1 import cycle_market as api
from app.core.auth import get_current_active_user
from app.database import get_db
from app.models.campaign import CampaignSeason
from app.models.clan import ClanMember
from app.models.cycle_market import CycleMarketCaravan, CycleMarketCommand, CycleMarketOffer
from app.services.campaign_cycle_store import CampaignCycleStore
from tests.test_cycle_market_service import market  # noqa: F401


@pytest.fixture
def client_world(db, market, monkeypatch):
    service, cycle, clans, wallets, now, _, _ = market
    db.add_all([ClanMember(clan_id=c.id, user_id=10 + i) for i, c in enumerate(clans)])
    db.add(ClanMember(clan_id=clans[0].id, user_id=90, is_trader=True))
    db.add(ClanMember(clan_id=clans[0].id, user_id=91, is_warlord=True))
    db.commit()
    monkeypatch.setattr(api, 'service', service)
    monkeypatch.setattr(api, 'utc_now', lambda: now)
    app = FastAPI()
    app.include_router(api.router, prefix='/api/v1/campaign/cycles')
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id=10, onboarding_completed_at=now)
    with TestClient(app) as client:
        yield client, app, market


def url(world, clan=0):
    _, _, market = world
    return f'/api/v1/campaign/cycles/market/cycles/{market[1].id}/clans/{market[2][clan].id}'


def terms(command='opaque: create / same retry'):
    return dict(command_id=command, expected_wallet_revision=1,
                offered={'iron': '2.5'}, requested={'wood': '3'})


def actor(app, user_id):
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id=user_id, onboarding_completed_at=True)


def test_decimal_reservation_retries_acceptance_and_private_transit(db, client_world):
    client, app, (_, cycle, clans, wallets, _, _, _) = client_world
    created = client.post(url(client_world) + '/offers', json=terms())
    assert created.status_code == 200, created.text
    offer = created.json()
    assert offer['offered']['iron'] == '2.5'
    assert (offer['first_full_cycle'], offer['expires_after_cycle']) == (1, 2)
    assert client.post(url(client_world) + '/offers', json=terms()).json() == offer
    assert Decimal(wallets[0].wallet['iron']) == Decimal('27.5')
    assert db.query(CycleMarketCommand).count() == 1
    public_url = url(client_world).rsplit('/clans/', 1)[0]
    actor(app, 12)
    public = client.get(public_url)
    assert public.status_code == 200
    assert public.json()['offers'] == [offer]
    assert 'wallet' not in public.text and 'gold' not in public.text
    assert client.get(url(client_world)).status_code == 403
    actor(app, 11)
    accept_url = url(client_world, 1) + f"/offers/{offer['id']}/accept"
    payload = dict(command_id='accept opaque', expected_revision=1,
                   expected_wallet_revision=1, expected_sender_revision=2)
    accepted = client.post(accept_url, json=payload)
    assert accepted.status_code == 200, accepted.text
    assert client.post(accept_url, json=payload).json() == accepted.json()
    assert db.query(CycleMarketCaravan).count() == 2
    assert client.get(public_url).json() == {'offers': []}
    own = client.get(url(client_world, 1)).json()
    assert len(own['caravans']) == 1
    saved = db.query(CycleMarketCaravan).filter_by(recipient_clan_id=clans[1].id).one()
    assert own['caravans'][0]['route'] == saved.route
    assert own['caravans'][0]['arrives_at'].startswith(saved.arrives_at.isoformat())
    assert saved.arrives_at - saved.departed_at == timedelta(hours=saved.route['travel_hours'])


def test_head_trader_only_and_cancel_retry(db, client_world):
    client, app, (_, _, _, wallets, _, _, _) = client_world
    for user in (12, 91):
        actor(app, user)
        assert client.post(url(client_world) + '/offers', json=terms()).status_code == 403
    actor(app, 90)
    response = client.post(url(client_world) + '/offers', json=terms())
    assert response.status_code == 200
    offer_id = response.json()['id']
    cancel_url = url(client_world) + f'/offers/{offer_id}/cancel'
    payload = dict(command_id='cancel', expected_revision=0, expected_wallet_revision=2)
    assert client.post(cancel_url, json=payload).status_code == 409
    payload['expected_revision'] = 1
    payload['command_id'] = terms()['command_id']
    assert client.post(cancel_url, json=payload).status_code == 409
    payload['command_id'] = 'cancel'
    assert client.post(cancel_url, json=payload).json()['status'] == 'cancelled'
    assert client.post(cancel_url, json=payload).status_code == 200
    assert Decimal(wallets[0].wallet['iron']) == 30


@pytest.mark.parametrize('cargo', [{'gold': '1'}, {'iron': '-1'}, {'iron': 'NaN'}, {'iron': 'Infinity'}])
def test_invalid_cargo_is_rejected(db, client_world, cargo):
    client, _, _ = client_world
    assert client.post(url(client_world) + '/offers', json={**terms(), 'offered': cargo}).status_code == 422
    assert db.query(CycleMarketOffer).count() == 0


def test_empty_cargo_and_stale_wallet_do_not_commit(db, client_world, monkeypatch):
    client, _, _ = client_world
    commits = []
    monkeypatch.setattr(db, 'commit', lambda: commits.append(True))
    for payload in ({**terms(), 'offered': {}}, {**terms(), 'expected_wallet_revision': 99}):
        assert client.post(url(client_world) + '/offers', json=payload).status_code == 409
    assert not commits
    assert db.query(CycleMarketOffer).count() == 0
    assert db.query(CycleMarketCommand).count() == 0


def test_auth_target_privacy_bogus_cycle_and_wrong_season(db, client_world):
    client, app, (_, cycle, clans, _, now, _, _) = client_world
    response = client.post(url(client_world) + '/offers', json={**terms(), 'target_clan_id': clans[1].id})
    offer_id = response.json()['id']
    public_url = url(client_world).rsplit('/clans/', 1)[0]
    assert client.get(public_url).json() == {'offers': []}
    actor(app, 12)
    assert client.post(url(client_world, 2) + f'/offers/{offer_id}/accept', json=dict(
        command_id='ineligible', expected_revision=1, expected_wallet_revision=1,
        expected_sender_revision=2)).status_code == 403
    assert client.get(public_url.replace(f'/{cycle.id}', '/99999')).status_code == 409
    db.get(CampaignSeason, cycle.season_id).status = 'ended'
    db.flush()
    other = CampaignSeason(number=2, name='Other', status='active', starts_at=now,
                           rules_snapshot={'version': 1, 'mechanics_version': 'cycle_v1'})
    db.add(other)
    db.flush()
    other_cycle = CampaignCycleStore().start(db, season_id=other.id)
    db.commit()
    actor(app, 10)
    wrong_url = url(client_world).replace(f'/cycles/{cycle.id}/', f'/cycles/{other_cycle.id}/')
    assert client.post(wrong_url + f'/offers/{offer_id}/cancel', json=dict(
        command_id='wrong-season', expected_revision=1, expected_wallet_revision=2)).status_code == 409
    def unauthorized():
        raise HTTPException(status_code=401)
    app.dependency_overrides[get_current_active_user] = unauthorized
    assert client.get(public_url).status_code == 401
    assert client.post(url(client_world) + '/offers', json=terms()).status_code == 401


@pytest.mark.parametrize('phase', ['battle', 'rest', 'ended'])
def test_manual_phase_gate_and_full_cycle_expiry(db, client_world, monkeypatch, phase):
    client, _, (_, cycle, _, _, _, _, _) = client_world
    timeline = CampaignCycleStore.timeline(cycle)
    now = timeline.battle_at + timedelta(hours=1)
    if phase in ('rest', 'ended'):
        now = timeline.replay_deadline
        cycle.settled_at = now
        cycle.season_end_requested = phase == 'ended'
        db.commit()
    monkeypatch.setattr(api, 'utc_now', lambda: now)
    response = client.post(url(client_world) + '/offers', json=terms())
    assert response.status_code == (409 if phase == 'ended' else 200), response.text
    if phase != 'ended':
        assert (response.json()['first_full_cycle'], response.json()['expires_after_cycle']) == (2, 3)


def test_no_trusted_hooks_are_routed(client_world):
    _, app, _ = client_world
    paths = list(app.openapi()['paths'])
    assert len(paths) == 6
    assert not any(hook in path for path in paths for hook in ('deliver', 'expire', 'hostile', 'war'))


def test_expired_projection_is_read_only(db, client_world, monkeypatch):
    client, _, (_, cycle, _, wallets, now, _, _) = client_world
    offer_id = client.post(url(client_world) + '/offers', json=terms()).json()['id']
    cycle.number = 2
    now = CampaignCycleStore.timeline(cycle).replay_deadline
    cycle.settled_at = now
    db.commit()
    monkeypatch.setattr(api, 'utc_now', lambda: now)
    public_url = url(client_world).rsplit('/clans/', 1)[0]
    assert client.get(public_url).json() == {'offers': []}
    assert client.get(url(client_world)).json()['offers'][0]['status'] == 'expired'
    assert db.get(CycleMarketOffer, offer_id).status == 'pending'
    assert Decimal(wallets[0].wallet['iron']) == Decimal('27.5')
    assert db.query(CycleMarketCommand).count() == 1


def test_failed_accept_rolls_back_all_writes(db, client_world, monkeypatch):
    client, app, (service, _, _, wallets, _, _, _) = client_world
    offer_id = client.post(url(client_world) + '/offers', json=terms()).json()['id']
    before = [dict(wallet.wallet) for wallet in wallets]
    original = service.economy._write
    calls = []
    commits = []

    def fail_second(db, row, **values):
        calls.append(row.id)
        if len(calls) == 2:
            raise ValueError('Injected second wallet failure')
        return original(db, row, **values)

    monkeypatch.setattr(service.economy, '_write', fail_second)
    monkeypatch.setattr(db, 'commit', lambda: commits.append(True))
    actor(app, 11)
    response = client.post(url(client_world, 1) + f'/offers/{offer_id}/accept', json=dict(
        command_id='failed-accept', expected_revision=1, expected_wallet_revision=1,
        expected_sender_revision=2))
    assert response.status_code == 409
    assert not commits
    assert [wallet.wallet for wallet in wallets] == before
    assert db.get(CycleMarketOffer, offer_id).status == 'pending'
    assert db.query(CycleMarketCaravan).count() == 0
    assert db.query(CycleMarketCommand).count() == 1


def test_changed_command_terms_and_legacy_season_rejected(db, client_world):
    client, _, (_, cycle, _, _, _, _, season) = client_world
    assert client.post(url(client_world) + '/offers', json=terms()).status_code == 200
    changed = {**terms(), 'requested': {'wood': '4'}}
    assert client.post(url(client_world) + '/offers', json=changed).status_code == 409
    season.rules_snapshot = {'mechanics_version': 'legacy'}
    db.commit()
    public_url = url(client_world).rsplit('/clans/', 1)[0]
    assert client.get(public_url).status_code == 409
    assert client.post(url(client_world) + '/offers', json=terms('new')).status_code == 409
