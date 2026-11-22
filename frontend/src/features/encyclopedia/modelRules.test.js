import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { levelStats, meshVisible } from './modelRules.js';

const catalog = JSON.parse(readFileSync(new URL('../../../public/encyclopedia/ennorath/catalog.json', import.meta.url)));

test('Aragorn progression preserves imported growth and clamps invalid levels', () => {
  const profile = catalog.profiles.find((item) => item.id === 'aragorn');
  assert.equal(levelStats(profile, 1).health, 3500);
  assert.equal(levelStats(profile, 10).health, 7300);
  assert.equal(levelStats(profile, 10).damage, 580);
  assert.deepEqual(levelStats(profile, 100), levelStats(profile, 10));
  assert.deepEqual(levelStats(profile, 0), levelStats(profile, 1));
});

test('buildings retain their original level cap and economic stat', () => {
  const profile = catalog.profiles.find((item) => item.id === 'rohanFarm');
  assert.equal(profile.maxLevel, 3);
  assert.deepEqual(levelStats(profile, 10), levelStats(profile, 3));
  assert.equal(profile.statLabels.damage, 'Макс. доход');
});

test('weapon and action rules preserve arrows, horn props and mesh exceptions', () => {
  assert.equal(meshVisible('ARROW', {}, { attackShowPrefixes: ['ARROW'] }, 'idle'), false);
  assert.equal(meshVisible('ARROW', {}, { attackShowPrefixes: ['ARROW'] }, 'attack'), true);
  assert.equal(meshVisible('BOX03', { hidePrefixes: ['BOX'], keepMeshes: ['BOX03'] }, null, 'idle'), true);
  assert.equal(meshVisible('HORN', { actionShowPrefixes: { horn: ['HORN'] } }, null, 'idle'), false);
  assert.equal(meshVisible('HORN', { actionShowPrefixes: { horn: ['HORN'] } }, null, 'horn'), true);
  assert.equal(meshVisible('CYLINDER02', { actionHide: { horn: ['CYLINDER02'] } }, null, 'horn'), false);
  assert.equal(meshVisible('CYLINDER02', { actionHideMeshes: { horn: ['CYLINDER02'] } }, null, 'horn'), false);
});
