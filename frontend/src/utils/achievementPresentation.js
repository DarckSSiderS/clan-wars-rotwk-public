const RARITY_TIERS = {
  common: 'bronze',
  uncommon: 'bronze',
  rare: 'silver',
  epic: 'gold',
  legendary: 'crystal',
  bronze: 'bronze',
  silver: 'silver',
  gold: 'gold',
  crystal: 'crystal',
};

const GENERAL_SYMBOLS = {
  first_battle: 'battle',
  first_win: 'victory',
  career_matches: 'battle',
  career_wins: 'victory',
  winning_streak: 'streak',
  battle_hardened: 'veteran',
  map_explorer: 'explore',
  faction_explorer: 'factions',
  long_battles: 'duration',
  fast_victories: 'speed',
  night_battles: 'night',
  different_opponents: 'opponents',
  active_days: 'active',
  team_games: 'team',
  team_wins: 'team-victory',
};

const hashText = (value) => {
  let hash = 2166136261;
  for (const character of String(value || 'achievement')) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash);
};

const initials = (value) => String(value || '?')
  .split(/[\s_():-]+/)
  .filter(Boolean)
  .slice(0, 2)
  .map((part) => part[0])
  .join('')
  .toLocaleUpperCase();

const subjectFromType = (type, prefix) => {
  const value = String(type || '');
  if (value.includes(':')) return value.split(':').slice(1).join(':');
  return value.replace(new RegExp(`^${prefix}_(games|wins|winrate)_?`), '').replaceAll('_', ' ');
};

export const normalizeAchievementTier = (rarity) => (
  RARITY_TIERS[String(rarity || '').toLocaleLowerCase()] || 'bronze'
);

export const getAchievementPresentation = (achievementType, fallbackName = '') => {
  const type = String(achievementType || '');
  const mapMatch = type.match(/^map_(games|wins|winrate)/);
  if (mapMatch) {
    const subject = subjectFromType(type, 'map');
    const hue = hashText(subject) % 360;
    return {
      kind: 'map',
      symbol: mapMatch[1],
      subject,
      glyph: initials(subject || fallbackName),
      accent: `hsl(${hue} 58% 52%)`,
    };
  }

  const factionMatch = type.match(/^faction_(games|wins|winrate)/);
  if (factionMatch) {
    const subject = subjectFromType(type, 'faction');
    return {
      kind: 'faction',
      symbol: factionMatch[1],
      subject,
      glyph: initials(subject || fallbackName),
      accent: `hsl(${hashText(subject) % 360} 58% 52%)`,
    };
  }

  const modeMatch = type.match(/^mode_(\dv\d)_(games|wins)$/);
  if (modeMatch) {
    return {
      kind: 'mode',
      symbol: modeMatch[2],
      subject: modeMatch[1],
      glyph: modeMatch[1],
      accent: '#d65f45',
    };
  }

  const normalizedType = type || fallbackName;
  return {
    kind: 'general',
    symbol: GENERAL_SYMBOLS[normalizedType] || 'medal',
    subject: fallbackName,
    glyph: initials(fallbackName),
    accent: '#c94d3f',
  };
};

export const getAchievementTitle = (achievement, t) => {
  const rawName = String(achievement?.name || '');
  const name = rawName.toLowerCase();
  if (name === 'first_battle') return t('achievement_card_first_battle', 'Первый бой');
  if (name === 'first_win') return t('achievement_card_first_win', 'Первая победа');
  const tier = name.match(/_(bronze|silver|gold|crystal)$/)?.[1];
  const type = String(achievement?.achievement_type || name.replace(/_(bronze|silver|gold|crystal)$/, ''));
  let titleKey = '';
  let subject = '';
  const subjectSeries = [
    ['faction_games:', 'achievement_card_faction_games'],
    ['faction_wins:', 'achievement_card_faction_wins'],
    ['faction_winrate:', 'achievement_card_faction_mastery'],
    ['map_games:', 'achievement_card_map_games'],
    ['map_wins:', 'achievement_card_map_wins'],
    ['map_winrate:', 'achievement_card_map_mastery'],
  ];
  const subjectMatch = subjectSeries.find(([prefix]) => type.startsWith(prefix));
  if (subjectMatch) {
    titleKey = subjectMatch[1];
    subject = type.slice(subjectMatch[0].length);
  } else {
    const modeMatch = type.match(/^mode_(\dv\d)_(games|wins)$/);
    if (modeMatch) {
      titleKey = modeMatch[2] === 'wins' ? 'achievement_card_mode_wins' : 'achievement_card_mode_games';
      subject = modeMatch[1];
    } else {
      titleKey = {
        career_matches: 'achievement_card_career_matches', career_wins: 'achievement_card_career_wins',
        winning_streak: 'achievement_card_winning_streak', battle_hardened: 'achievement_card_battle_hardened',
        map_explorer: 'achievement_card_map_explorer', faction_explorer: 'achievement_card_faction_explorer',
        long_battles: 'achievement_card_long_battles', fast_victories: 'achievement_card_fast_victories',
        night_battles: 'achievement_card_night_battles', different_opponents: 'achievement_card_different_opponents',
        active_days: 'achievement_card_active_days', team_games: 'achievement_card_team_games', team_wins: 'achievement_card_team_wins',
      }[type] || '';
    }
  }
  if (!titleKey) return rawName.replaceAll('_', ' ');
  const parts = [t(titleKey, rawName.replaceAll('_', ' '))];
  if (subject) parts.push(subject);
  if (tier) parts.push(t(`achievement_tier_${tier}`, tier));
  return parts.join(' · ');
};
