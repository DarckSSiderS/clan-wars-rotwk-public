import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { getMessages } from '../src/i18n/messages.js';
import {
  CLAN_WAR_HANDBOOK_SECTION_IDS,
  getClanWarHandbook,
} from '../src/content/clanWarHandbook.js';
import { getPublicDocument } from '../src/content/publicDocuments.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const messages = getMessages();
const errors = [];
const languageCodes = ['ru', 'en', 'de'];
const cyrillicPattern = /[А-Яа-яЁё]/u;

const placeholders = (text) => (
  [...text.matchAll(/\{([A-Za-z][A-Za-z0-9_]*)\}/g)]
    .map((match) => match[1])
    .sort()
);

for (const [key, translations] of Object.entries(messages)) {
  if (!Array.isArray(translations) || translations.length !== 3) {
    errors.push(`${key}: требуется ровно три перевода (ru, en, de)`);
    continue;
  }
  translations.forEach((text, index) => {
    if (typeof text !== 'string' || !text.trim()) {
      errors.push(`${key}: отсутствует перевод ${languageCodes[index]}`);
    } else if (index > 0 && cyrillicPattern.test(text)) {
      errors.push(`${key}: в переводе ${languageCodes[index]} остался кириллический текст`);
    }
  });

  if (translations.every((text) => typeof text === 'string')) {
    const expected = placeholders(translations[0]).join(',');
    translations.slice(1).forEach((text, index) => {
      const actual = placeholders(text).join(',');
      if (actual !== expected) {
        errors.push(
          `${key}: параметры ${languageCodes[index + 1]} (${actual || 'нет'}) `
          + `не совпадают с ru (${expected || 'нет'})`,
        );
      }
    });
  }
}

const checkLocalizedData = (label, value, language) => {
  if (!value || typeof value !== 'object') {
    errors.push(`${label}: отсутствуют данные ${language}`);
    return;
  }
  if (language !== 'ru' && cyrillicPattern.test(JSON.stringify(value))) {
    errors.push(`${label}: в данных ${language} остался кириллический текст`);
  }
};

languageCodes.forEach((language) => {
  const handbook = getClanWarHandbook(language);
  checkLocalizedData('Справочник ClanWars', handbook, language);
  const handbookSectionIds = new Set((handbook.categories || []).map((category) => category.id));
  CLAN_WAR_HANDBOOK_SECTION_IDS.forEach((sectionId) => {
    if (!handbookSectionIds.has(sectionId)) {
      errors.push(`Справочник ClanWars: в ${language} отсутствует раздел ${sectionId}`);
    }
  });

  ['gettingStarted', 'economy', 'privacy', 'overview'].forEach((documentId) => {
    checkLocalizedData(
      `Публичный документ ${documentId}`,
      getPublicDocument(language, documentId),
      language,
    );
  });
});

const sourceFiles = [];
const collectFiles = (directory) => {
  readdirSync(directory).forEach((name) => {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) collectFiles(path);
    else if (/\.(jsx?|tsx?)$/.test(name) && !path.endsWith('messages.js')) sourceFiles.push(path);
  });
};
collectFiles(root);

const callPattern = /(?:getLocalizedText|getTextSync|\bt)\(\s*['"]([^'"]+)['"]/g;
sourceFiles.forEach((path) => {
  const source = readFileSync(path, 'utf8');
  for (const match of source.matchAll(callPattern)) {
    if (!messages[match[1]]) {
      errors.push(`${relative(root, path)}: ключ ${match[1]} не имеет полного перевода ru/en/de`);
    }
  }
});

if (errors.length) {
  console.error('Проверка локализации не пройдена:\n' + errors.map((item) => `- ${item}`).join('\n'));
  process.exit(1);
}

console.log(`Локализация проверена: ${Object.keys(messages).length} ключей, ru/en/de заполнены.`);
