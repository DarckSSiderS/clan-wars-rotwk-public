export const FACTIONS = [
  'Люди',
  'Эльфы',
  'Гоблины',
  'Гномы',
  'Мордор',
  'Изенгард',
  'Ангмар',
  'Гондор',
  'Рохан',
  'Арнор',
  'Харад',
  'Лотлориэн',
  'Имладрис',
  'Мглистые Горы',
  'Рун',
];

export const FACTIONS_BY_PATCH = {
  ennorath: [
    'Гондор',
    'Арнор',
    'Рохан',
    'Лотлориэн',
    'Имладрис',
    'Гномы',
    'Изенгард',
    'Мордор',
    'Мглистые Горы',
    'Ангмар',
    'Харад',
    'Рун',
  ],
  patch_202: ['Люди', 'Эльфы', 'Гномы', 'Изенгард', 'Мордор', 'Гоблины', 'Ангмар'],
};

const FACTION_ALIASES = {
  люди: 'all',
  men: 'all',
  эльфы: 'all',
  elves: 'all',
  гоблины: 'goblins',
  goblins: 'goblins',
  гномы: 'dwarves',
  dwarves: 'dwarves',
  мордор: 'mordor',
  mordor: 'mordor',
  изенгард: 'isengard',
  isengard: 'isengard',
  ангмар: 'angmar',
  angmar: 'angmar',
  гондор: 'gondor',
  gondor: 'gondor',
  рохан: 'rohan',
  rohan: 'rohan',
  арнор: 'arnor',
  arnor: 'arnor',
  харад: 'harad',
  harad: 'harad',
  лотлориэн: 'lothlorien',
  lothlorien: 'lothlorien',
  имладрис: 'imladris',
  imladris: 'imladris',
  'мглистые горы': 'goblins',
  'misty mountains': 'goblins',
  рун: 'rhun',
  rhun: 'rhun',
};

export const getFactionSlug = (faction) => {
  const normalized = String(faction || '').trim().toLocaleLowerCase('ru-RU');
  return FACTION_ALIASES[normalized] || 'all';
};

export const getFactionIcon = (faction, size = 'small') => {
  const directory = size === 'large' ? '1' : '2';
  return `/icons/factions/${directory}/${getFactionSlug(faction)}.png`;
};

export const getFactionTone = (faction) => getFactionSlug(faction);

const FACTION_NAMES = {
  'люди': ['Люди', 'Men', 'Menschen'],
  men: ['Люди', 'Men', 'Menschen'],
  'эльфы': ['Эльфы', 'Elves', 'Elben'],
  elves: ['Эльфы', 'Elves', 'Elben'],
  'гоблины': ['Гоблины', 'Goblins', 'Goblins'],
  goblins: ['Гоблины', 'Goblins', 'Goblins'],
  'гномы': ['Гномы', 'Dwarves', 'Zwerge'],
  dwarves: ['Гномы', 'Dwarves', 'Zwerge'],
  'мордор': ['Мордор', 'Mordor', 'Mordor'],
  mordor: ['Мордор', 'Mordor', 'Mordor'],
  'изенгард': ['Изенгард', 'Isengard', 'Isengart'],
  isengard: ['Изенгард', 'Isengard', 'Isengart'],
  'ангмар': ['Ангмар', 'Angmar', 'Angmar'],
  angmar: ['Ангмар', 'Angmar', 'Angmar'],
  'гондор': ['Гондор', 'Gondor', 'Gondor'],
  gondor: ['Гондор', 'Gondor', 'Gondor'],
  'рохан': ['Рохан', 'Rohan', 'Rohan'],
  rohan: ['Рохан', 'Rohan', 'Rohan'],
  'арнор': ['Арнор', 'Arnor', 'Arnor'],
  arnor: ['Арнор', 'Arnor', 'Arnor'],
  'харад': ['Харад', 'Harad', 'Harad'],
  harad: ['Харад', 'Harad', 'Harad'],
  'лотлориэн': ['Лотлориэн', 'Lothlórien', 'Lothlórien'],
  lothlorien: ['Лотлориэн', 'Lothlórien', 'Lothlórien'],
  'имладрис': ['Имладрис', 'Imladris', 'Imladris'],
  imladris: ['Имладрис', 'Imladris', 'Imladris'],
  'мглистые горы': ['Мглистые Горы', 'Misty Mountains', 'Nebelgebirge'],
  'misty mountains': ['Мглистые Горы', 'Misty Mountains', 'Nebelgebirge'],
  'рун': ['Рун', 'Rhûn', 'Rhûn'],
  rhun: ['Рун', 'Rhûn', 'Rhûn'],
};

export const getFactionName = (faction, language = 'ru') => {
  const normalized = String(faction || '').trim().toLocaleLowerCase('ru-RU');
  const index = language === 'de' ? 2 : language === 'en' || language === 'eng' ? 1 : 0;
  return FACTION_NAMES[normalized]?.[index] || faction;
};
