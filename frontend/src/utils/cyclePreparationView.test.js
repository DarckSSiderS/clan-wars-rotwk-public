import test from 'node:test';
import assert from 'node:assert/strict';
import { scoutOrderAvailable } from './cyclePreparationView.js';

const data = { territories: [{ id: 10 }], scout: { can_request: true, request: null, wallet_revision: 5,
  players: [{ user_id: 42, name: 'Display only', external_uuid: 'arena-42' }] } };
const payload = { territory_id: 10, scout_user_id: 42, expected_revision: 5 };

test('scout confirmation needs a current free member, target and wallet revision', () => {
  assert.equal(scoutOrderAvailable(data, payload), true);
  for (const invalid of [null, { ...payload, scout_user_id: null }, { ...payload, scout_user_id: 99 },
    { ...payload, territory_id: 99 }, { ...payload, expected_revision: 4 }]) {
    assert.equal(scoutOrderAvailable(data, invalid), false);
  }
  for (const scout of [{ players: [] }, { can_request: false }, { request: { scout_user_id: 42 } }, { wallet_revision: undefined }]) {
    assert.equal(scoutOrderAvailable({ ...data, scout: { ...data.scout, ...scout } }, payload), false);
  }
  assert.equal(scoutOrderAvailable(null, payload), false);
});
