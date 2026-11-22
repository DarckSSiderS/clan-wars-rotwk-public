export function archiveEndpoint(seasonId) {
  const base = '/api/v1/campaign/archives';
  if (seasonId === undefined) return base;
  if (!/^[1-9]\d*$/.test(String(seasonId)) || !Number.isSafeInteger(Number(seasonId))) {
    throw new TypeError('Invalid archive ID');
  }
  return `${base}/${seasonId}`;
}

export function archiveMapUrl(url, seasonId) {
  return url === `${archiveEndpoint(seasonId)}/map.svg` ? url : null;
}

export function archiveAwardUrl(url) {
  return typeof url === 'string' && /^\/assets\/awards\/clan\/[a-zA-Z0-9_-]+\.(png|webp|jpg|svg)$/.test(url) ? url : null;
}

export function archiveViewBox(value) {
  const values = typeof value === 'string' ? value.trim().split(/[\s,]+/).map(Number) : [];
  if (values.length !== 4 || !values.every(Number.isFinite) || values[2] <= 0 || values[3] <= 0) {
    throw new TypeError('Invalid archive viewBox');
  }
  const [x, y, width, height] = values;
  return { x, y, width, height };
}

export const archiveClans = clans => [...clans].sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity));

export function archiveClanColor(clan) {
  const color = clan?.clan_map_color;
  return typeof color === 'string' && /^(#[\da-f]{3,8}|rgba?\([\d.,%\s]+\)|hsla?\([\d.,%\s]+\)|[a-z]+)$/i.test(color)
    && !['inherit', 'initial', 'unset', 'currentcolor'].includes(color.toLowerCase()) ? color : '#89938b';
}

export const isArchiveInterseason = navigation => navigation?.interseason === true || navigation?.mode === 'interseason';
