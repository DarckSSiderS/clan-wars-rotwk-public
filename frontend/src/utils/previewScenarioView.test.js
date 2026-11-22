import { test } from 'node:test';
import assert from 'node:assert/strict';
import { previewScenarioReturnPath } from './previewScenarioView.js';

test('preview scenario switch keeps map and clan tabs, replaces only a cycle id', () => {
  assert.equal(previewScenarioReturnPath('/map', '?territory=3', 4), '/map?territory=3');
  assert.equal(previewScenarioReturnPath('/clans/7', '?tab=barter', 4), '/clans/7?tab=barter');
  assert.equal(previewScenarioReturnPath('/campaign/cycles/2/orders', '', 4), '/campaign/cycles/4/orders');
  assert.equal(previewScenarioReturnPath('//external.example', '', 4), '/map');
  assert.throws(() => previewScenarioReturnPath('/map', '', '../api'));
});
