import assert from 'node:assert/strict';
import test from 'node:test';

import {
  CLAN_COLORS,
  CLAN_TERRITORY_HOVER_OPACITY,
  CLAN_TERRITORY_OPACITY,
  CLAN_TERRITORY_SELECTED_OPACITY,
  CLAN_TERRITORY_STROKE,
  getClanTerritoryPaint,
} from './clanColors.js';

test('exposes the approved 24-color map palette', () => {
    assert.equal(CLAN_COLORS.length, 24);
    assert.deepEqual(CLAN_COLORS, [
      '#D32F2F', '#E64A19', '#F57C00', '#FFB300', '#FBC02D', '#C0CA33',
      '#7CB342', '#43A047', '#2E7D32', '#00897B', '#00ACC1', '#039BE5',
      '#1E88E5', '#3949AB', '#5E35B1', '#8E24AA', '#D81B60', '#C2185B',
      '#6D4C41', '#8D6E63', '#546E7A', '#455A64', '#9E9D24', '#AD1457',
    ]);
});

test('uses calm ownership fill and a fixed dark border', () => {
    assert.deepEqual(getClanTerritoryPaint('#D32F2F'), {
      fill: 'rgba(211, 47, 47, 0.8)',
      hoverFill: 'rgba(211, 47, 47, 0.9)',
      selectedFill: 'rgba(211, 47, 47, 0.6)',
      stroke: CLAN_TERRITORY_STROKE,
    });
    assert.equal(CLAN_TERRITORY_OPACITY, 0.8);
    assert.equal(CLAN_TERRITORY_HOVER_OPACITY, 0.9);
    assert.equal(CLAN_TERRITORY_SELECTED_OPACITY, 0.6);
});
