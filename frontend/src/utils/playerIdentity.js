const INTERNAL_USERNAME_SUFFIX = /~[0-9a-f]{8,64}(?:~\d+)?$/i;

const cleanText = (value) => String(value || '').trim();
const normalizePlayer = (player) => (
  typeof player === 'string' ? { username: player } : (player || {})
);

export const getPlayerDisplayName = (player, fallback = '') => {
  const normalizedPlayer = normalizePlayer(player);
  const explicitName = cleanText(normalizedPlayer.display_name) || cleanText(normalizedPlayer.nickname);
  if (explicitName) return explicitName;

  const username = cleanText(normalizedPlayer.username);
  return username.replace(INTERNAL_USERNAME_SUFFIX, '') || cleanText(fallback);
};

export const getPlayerProfilePath = (player) => {
  const normalizedPlayer = normalizePlayer(player);
  const canonicalName = cleanText(normalizedPlayer.display_name)
    || cleanText(normalizedPlayer.username).replace(INTERNAL_USERNAME_SUFFIX, '');
  return `/profile/${encodeURIComponent(canonicalName)}`;
};
