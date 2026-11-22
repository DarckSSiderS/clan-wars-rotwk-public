import test from 'node:test';
import assert from 'node:assert/strict';
import { barterFee, rememberBarterCommand, forgetBarterCommand } from './cycleBarterCommands.js';
test('uncertain command survives a component remount but is scoped to its actor', () => {
  const map = new Map(); const storage = { getItem: k => map.get(k), setItem: (k,v) => map.set(k,v) };
  assert.equal(rememberBarterCommand(storage, 'actor:1', 'terms', () => 'first'), 'first');
  assert.equal(rememberBarterCommand(storage, 'actor:1', 'terms', () => 'second'), 'first');
  assert.equal(rememberBarterCommand(storage, 'actor:2', 'terms', () => 'other'), 'other');
  forgetBarterCommand(storage, 'actor:1', 'terms');
  assert.equal(rememberBarterCommand(storage, 'actor:1', 'terms', () => 'new'), 'new');
});
test('creator fee retains exact decimal precision without floating point arithmetic', () => {
  assert.equal(barterFee({ mithril: '1' }, { mithril: '300' }), '30');
  assert.equal(barterFee({ iron: '0.000001' }, { iron: '45' }), '0.0000045');
  assert.equal(barterFee({ wood: '3', iron: '2.5' }, { wood: '40', iron: '45' }), '23.25');
});
