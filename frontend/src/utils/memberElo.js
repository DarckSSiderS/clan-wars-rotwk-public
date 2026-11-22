export const getMemberEloRatings = (stats = {}) => ({
  ennorath: stats.elo_ratings?.ennorath ?? '—',
  patch202: stats.elo_ratings?.patch_202 ?? '—',
});

export const getMemberEloForPatch = (stats = {}, patch = 'ennorath') => (
  stats.elo_ratings?.[patch] ?? '—'
);
