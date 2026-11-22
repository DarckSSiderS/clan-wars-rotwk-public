export const CLAN_COLORS = [
  '#D32F2F', '#E64A19', '#F57C00', '#FFB300', '#FBC02D', '#C0CA33',
  '#7CB342', '#43A047', '#2E7D32', '#00897B', '#00ACC1', '#039BE5',
  '#1E88E5', '#3949AB', '#5E35B1', '#8E24AA', '#D81B60', '#C2185B',
  '#6D4C41', '#8D6E63', '#546E7A', '#455A64', '#9E9D24', '#AD1457',
];

export const CLAN_TERRITORY_OPACITY = 0.8;
export const CLAN_TERRITORY_HOVER_OPACITY = 0.9;
export const CLAN_TERRITORY_SELECTED_OPACITY = 0.6;
export const CLAN_TERRITORY_STROKE = '#1F1F1F';

export const colorWithAlpha = (hex, alpha) => {
  const normalized = String(hex || '').replace('#', '');
  if (!/^[0-9a-f]{6}$/i.test(normalized)) return `rgba(98, 98, 112, ${alpha})`;
  const value = Number.parseInt(normalized, 16);
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
};

export const getClanTerritoryPaint = (color) => ({
  fill: colorWithAlpha(color, CLAN_TERRITORY_OPACITY),
  hoverFill: colorWithAlpha(color, CLAN_TERRITORY_HOVER_OPACITY),
  selectedFill: colorWithAlpha(color, CLAN_TERRITORY_SELECTED_OPACITY),
  stroke: CLAN_TERRITORY_STROKE,
});
