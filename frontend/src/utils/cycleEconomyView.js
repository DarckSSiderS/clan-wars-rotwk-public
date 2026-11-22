const messages = {
  trade: ['Торговля', 'Trade'], tradeMode: ['Режим торговли', 'Trade mode'], goldMarket: ['Рынок за золото', 'Gold market'],
  starterHelp: ['Выберите 2 реликвии в подарок: каждая достанется клану бесплатно на первом уровне. Получение подарка не активирует реликвию. Активный набор выбирается отдельно.', 'Choose 2 free level-one relics for your clan. Claiming a gift does not activate it. Choose the active loadout separately.'],
  currentEffect: ['Сейчас', 'Current'], nextEffect: ['Следующий уровень', 'Next level'],
  goldShort: ['Золото', 'Gold'], profileShort: ['Добыча', 'Production'], mithrilShort: ['Мифрил', 'Mithril'], fortificationShort: ['Укрепления', 'Fortifications'], offenseShort: ['Наступление', 'Offense'], navalShort: ['Флот', 'Fleet'],
  give: ['Отдаёте', 'You give'], receive: ['Получаете', 'You receive'], total: ['Итого', 'Total'],
  barter: ['Межклановый обмен', 'Clan barter'],
  levelShort: ['Ур.', 'Lvl'],
  heading: ['Казна и развитие', 'Treasury and development'], relics: ['Реликвии', 'Relics'], lands: ['Территории', 'Territories'], market: ['Рынок', 'Market'],
  gold: ['Золото', 'Gold'], iron: ['Железо', 'Iron'], wood: ['Дерево', 'Wood'], food: ['Еда', 'Food'], mithril: ['Мифрил', 'Mithril'],
  init: ['Получить стартовую казну', 'Claim starting treasury'], loading: ['Загрузка казны...', 'Loading treasury...'], refresh: ['Обновить', 'Refresh'],
  failed: ['Не удалось загрузить казну.', 'Could not load treasury.'], clanless: ['Вступите в клан для просмотра казны.', 'Join a clan to view its treasury.'],
  saved: ['Изменения сохранены.', 'Changes saved.'], conflict: ['Результат не подтверждён. Проверьте обновлённую казну перед следующим действием.', 'Result not confirmed. Check the refreshed treasury before the next action.'],
  starters: ['Выберите две бесплатные реликвии первого уровня', 'Choose two free level-one relics'], claim: ['Получить выбранные реликвии', 'Claim selected relics'],
  active: ['Активная реликвия', 'Active relic'], starter: ['В подарок · ур. 1', 'Free gift · lvl 1'], save: ['Сохранить активный набор', 'Save active set'],
  frozen: ['Набор меняется только в подготовку и перерыв. В текущем сражении действуют эффекты, закреплённые на его старте.', 'Change the loadout during preparation and rest. Current battles use effects frozen at their start.'],
  buy: ['Купить', 'Buy'], upgrade: ['Улучшить', 'Upgrade'], max: ['Максимальный уровень', 'Maximum level'], level: ['Уровень', 'Level'], effect: ['Эффект', 'Effect'], price: ['Цена перехода', 'Transition price'],
  goldBranch: ['Золотая добыча', 'Gold production'], profile: ['Профильная добыча', 'Profile production'], mithrilBranch: ['Добыча мифрила', 'Mithril production'],
  fortification: ['Укрепления', 'Fortifications'], offense: ['Наступление', 'Offense'], naval: ['Морская инфраструктура', 'Naval infrastructure'],
  unavailable: ['Недоступно на этой земле', 'Unavailable on this territory'], noLands: ['У клана нет территорий.', 'Your clan has no territories.'],
  resource: ['Ресурс', 'Resource'], quantity: ['Количество', 'Quantity'], buying: ['Покупка', 'Purchase'], selling: ['Продажа', 'Sale'], direction: ['Операция', 'Operation'],
  unit: ['Цена за единицу', 'Unit price'], perform: ['Подтвердить обмен с рынком', 'Confirm market exchange'],
  confirm: ['Подтвердить покупку?', 'Confirm purchase?'], confirmAction: ['Подтвердить', 'Confirm'], cancel: ['Отмена', 'Cancel'],
  daily: ['в сутки', 'per day'], territoryGold: ['Доход золота с территорий', 'Territory gold income'], influence: ['Влияние клана', 'Clan influence'],
  territorial_victory: ['Очки за победы в территориальных битвах', 'Territorial battle victory points'], attack_victory: ['Очки побед при атаке', 'Attacking victory points'],
  defense_victory: ['Очки побед при обороне', 'Defending victory points'], economic_gold_discount: ['Скидка золотом на экономические улучшения', 'Gold discount on economic upgrades'],
  allied_help_victory: ['Очки побед при помощи союзнику', 'Allied help victory points'], fortress_defense_victory: ['Очки побед при защите крепости', 'Fortress defense victory points'],
  interception_victory: ['Очки побед в перехвате', 'Interception victory points'], direct_defense_victory: ['Очки очных побед при обороне', 'Direct defense victory points'],
  fortification_material_discount: ['Скидка железом и деревом на укрепления', 'Iron and wood discount on fortifications'],
};
export const economyMessage = (key, language) => (messages[key] || messages.unavailable)[String(language).startsWith('en') ? 1 : 0];
export const resources = ['gold', 'iron', 'wood', 'food', 'mithril'];
export const costText = (cost, copy) => resources.filter(k => Number(cost?.[k]) > 0).map(k => `${cost[k]} ${copy(k)}`).join(' · ');
export const canAfford = (wallet, cost) => Boolean(cost && resources.every(k => Number(wallet?.[k] || 0) >= Number(cost[k] || 0)));
export const positiveQuantity = value => /^(?:0|[1-9]\d*)(?:\.\d{1,6})?$/.test(String(value)) && Number(value) > 0;

// Presentation mirror of cycle_economy.UPGRADES; prices always come from API quotes.
const upgradeEffects = { gold: ['35', '115', '265'], profile: ['2', '5', '10'], mithril: ['0.5', '1.25', '2.5'], fortification: ['5', '10', '20'], offense: ['5', '10', '20'], naval: ['5', '10', '20'] };
export const currentUpgradeEffect = (branch, quote) => quote.current_effect ?? (quote.level ? upgradeEffects[branch]?.[quote.level - 1] : '0');
export const upgradeEffectText = (branch, value, copy) => value == null ? '-' : `+${value}${['fortification', 'offense', 'naval'].includes(branch) ? '%' : ` ${copy('daily')}`}`;
export function marketTotal(quantity, price) {
  if (!positiveQuantity(quantity) || !/^\d+$/.test(String(price))) return null;
  const [whole, fraction = ''] = String(quantity).split('.');
  const amount = (BigInt(whole) * 1_000_000n + BigInt(fraction.padEnd(6, '0'))) * BigInt(price);
  const tail = (amount % 1_000_000n).toString().padStart(6, '0').replace(/0+$/, '');
  return `${amount / 1_000_000n}${tail ? `.${tail}` : ''}`;
}
