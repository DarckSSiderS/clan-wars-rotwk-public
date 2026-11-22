const words = {
  nav: 'навигация',
  page: 'страница',
  profile: 'профиль',
  tab: 'вкладка',
  clan: 'клан',
  clans: 'кланы',
  member: 'участник',
  members: 'участники',
  list: 'список',
  stats: 'статистика',
  statistics: 'статистика',
  role: 'роль',
  level: 'уровень',
  matches: 'матчи',
  match: 'матч',
  player: 'игрок',
  players: 'игроки',
  achievements: 'достижения',
  achievement: 'достижение',
  quests: 'задания',
  quest: 'задание',
  settings: 'настройки',
  search: 'поиск',
  loading: 'загрузка',
  error: 'ошибка',
  no: 'нет',
  data: 'данных',
  created: 'создан',
  wins: 'победы',
  losses: 'поражения',
  win: 'победа',
  rate: 'процент',
  view: 'открыть',
  button: 'кнопка',
};

export const readableText = (identifier) => String(identifier || '')
  .split('_')
  .map((word) => words[word.toLowerCase()] || word)
  .join(' ')
  .replace(/^./, (letter) => letter.toUpperCase());
