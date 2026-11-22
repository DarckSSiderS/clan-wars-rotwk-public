import { groupContributions, sumScores } from './cycleBattleView.js';

export function territoryMatchFeed(battle) {
  const metadata = new Map((battle.matches || []).map(match => [match.replay_id, match]));
  return groupContributions(battle.contributions).map(group => {
    const detail = metadata.get(group.replay_id) || {};
    const teams = new Map(), effects = new Map();
    for (const player of detail.participants || []) {
      if (!teams.has(player.team)) teams.set(player.team, { id: player.team, players: [] });
      teams.get(player.team).players.push(player);
    }
    for (const row of group.contributions) {
      if (!effects.has(row.clan_id)) effects.set(row.clan_id, []);
      effects.get(row.clan_id).push(row);
    }
    const counted = group.contributions.filter(row => row.counted).length;
    return { ...group, ...detail,
      played_at: group.contributions.find(row => row.calculation?.started_at)?.calculation.started_at || detail.played_at,
      status: counted === group.contributions.length ? 'counted' : counted ? 'mixed' : 'rejected',
      teams: [...teams.values()].map(team => ({ ...team, is_winner: team.players.every(p => p.is_winner === true) ? true : team.players.every(p => p.is_winner === false) ? false : null })),
      effects: [...effects].map(([clan_id, rows]) => ({ clan_id,
        clan_name: battle.sides?.find(side => side.clan_id === clan_id)?.clan_name,
        points: sumScores(rows.filter(row => row.counted).map(row => row.points)) })),
    };
  }).sort((a, b) => (Date.parse(b.played_at) || 0) - (Date.parse(a.played_at) || 0));
}

export function matchFeedCounts(matches) {
  return { all: matches.length, counted: matches.filter(m => m.status !== 'rejected').length,
    rejected: matches.filter(m => m.status === 'rejected').length };
}

export function battleKind(battle) {
  const attacks = (battle.sides || []).filter(side => side.role === 'attack').length;
  return !attacks ? 'defenseOnly' : (battle.sides?.length === 1 && battle.owner_clan_id == null) ? 'neutralClaim' : 'contested';
}

export const signedScore = value => String(value).startsWith('-') || Number(value) === 0 ? String(value) : `+${value}`;
const messages = {
  defenseOnly: ['Оборона без нападения', 'Uncontested defence'], neutralClaim: ['Занятие нейтральной земли', 'Neutral land claim'],
  contested: ['Сражение за землю', 'Territory battle'], owner: ['Владелец до сражения', 'Owner before battle'], neutral: ['Нейтральная земля', 'Neutral land'],
  winner: ['Победа', 'Victory'], loser: ['Поражение', 'Defeat'], team: ['Команда', 'Team'], vs: ['против', 'versus'],
  match: ['Матч', 'Match'], counted: ['Засчитан', 'Counted'], mixed: ['Частично засчитан', 'Partially counted'], rejected: ['Не засчитан', 'Not counted'],
  contribution: ['Изменение счёта кланов', 'Clan score changes'], unavailable: ['Полный состав матча недоступен', 'Full match lineup unavailable'],
  mapUnknown: ['Карта не указана', 'Map unavailable'], all: ['Все матчи', 'All matches'], onlyCounted: ['С зачётом', 'Counted'], onlyRejected: ['Без зачёта', 'Rejected'],
  overview: ['Сражения кланов', 'Clan battles'], lands: ['Сражения за земли', 'Territory battles'], involved: ['Участвуют', 'Participants'],
  score: ['Очки за землю', 'Territory score'], playerScores: ['Вклад игроков', 'Player contributions'], matches: ['Матчей', 'Matches'],
  active: ['Сражение идёт', 'Battle ongoing'], settled: ['Итог подведён', 'Battle settled'], pending: ['Ожидает расчёта', 'Awaiting settlement'],
  feedEmpty: ['Матчей по этим условиям нет', 'No matches match this filter'],
};
export const matchMessage = (key, language) => (messages[key] || [key, key])[String(language).startsWith('en') ? 1 : 0];
