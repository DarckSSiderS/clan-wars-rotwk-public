from tests.test_cycle_market_api import client_world, url, terms, actor
from tests.test_cycle_market_service import market


def test_acceptance_quote_returns_revisions_fee_and_route_without_foreign_wallet(db, client_world):
    client, app, _ = client_world
    offer = client.post(url(client_world) + '/offers', json=terms()).json()
    actor(app, 11)
    quote = client.get(url(client_world, 1) + f"/offers/{offer['id']}/quote")
    assert quote.status_code == 200
    data = quote.json()
    assert data['expected_revision'] == 1
    assert data['expected_sender_revision'] == 2
    assert data['expected_wallet_revision'] == 1
    assert data['fee_gold'] == '11.25'
    assert 'wallet' not in {key for key in data if key != 'expected_wallet_revision'}
    assert 'balance' not in data


def test_quote_does_not_spend_or_create_receipts_and_rejects_the_sender(db, client_world):
    from app.models.cycle_market import CycleMarketCommand, CycleMarketCaravan
    client, app, (_, _, _, wallets, _, _, _) = client_world
    offer = client.post(url(client_world) + '/offers', json=terms()).json()
    balances = [dict(wallet.wallet) for wallet in wallets]
    receipts = db.query(CycleMarketCommand).count()
    quote_path = f"/offers/{offer['id']}/quote"
    assert client.get(url(client_world) + quote_path).status_code == 403
    actor(app, 11)
    assert client.get(url(client_world, 1) + quote_path).status_code == 200
    assert [dict(wallet.wallet) for wallet in wallets] == balances
    assert db.query(CycleMarketCommand).count() == receipts
    assert db.query(CycleMarketCaravan).count() == 0
