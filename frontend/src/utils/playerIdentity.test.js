import assert from 'node:assert/strict';
import test from 'node:test';

import { getPlayerDisplayName, getPlayerProfilePath } from './playerIdentity.js';

test('prefers the Arena display name over the internal username', () => {
  assert.equal(getPlayerDisplayName({
    username: 'fatcat~367fb5b7',
    display_name: 'fatcat',
  }), 'fatcat');
});

test('removes a deterministic collision suffix when no display name is available', () => {
  assert.equal(getPlayerDisplayName({ username: 'fatcat~367fb5b7' }), 'fatcat');
  assert.equal(getPlayerDisplayName({ username: 'fatcat~367fb5b7~2' }), 'fatcat');
});

test('preserves a regular nickname containing a tilde', () => {
  assert.equal(getPlayerDisplayName({ username: 'fatcat~pro' }), 'fatcat~pro');
});

test('builds the public profile URL from the clean Arena nickname', () => {
  assert.equal(getPlayerProfilePath({
    username: 'fatcat~367fb5b7',
    display_name: 'fat cat',
  }), '/profile/fat%20cat');
});

test('does not use a non-canonical presentation nickname in the profile URL', () => {
  assert.equal(getPlayerProfilePath({
    username: 'paint-owner',
    nickname: 'Paint Owner',
  }), '/profile/paint-owner');
});
