import { formatScore } from './cycleBattleView.js';

export function clanCycleBattle(battle, clanId) {
  const sides = battle.sides || [];
  const own = sides.find(side => String(side.clan_id) === String(clanId));
  return { ...battle, href: `/campaign/cycles/${battle.cycle_id}?territory=${battle.territory_id}`,
    ownScore: formatScore(own?.score ?? '0'), opponents: sides.filter(side => String(side.clan_id) !== String(clanId))
      .map(side => ({ ...side, score: formatScore(side.score ?? '0') })),
    result: !battle.completed_at ? 'active' : battle.winner_clan_id == null ? 'draw'
      : String(battle.winner_clan_id) === String(clanId) ? 'win' : 'loss' };
}

export function currentClanBattles(history) {
  return (history?.battles || []).filter(row => row.season_id === history.season_id);
}

const messages = {
  archive: ['Архив старых войн', 'Legacy wars archive'],
  unavailable: ['Не удалось загрузить историю сражений', 'Battle history could not be loaded'],
  active: ['Без итогов', 'Unsettled'], win: ['Победа', 'Victory'], loss: ['Поражение', 'Defeat'], draw: ['Без победителя', 'No winner'],
};
export const clanHistoryMessage = (key, language) => (messages[key] || messages.unavailable)[String(language).startsWith('en') ? 1 : 0];
