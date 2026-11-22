import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from '@babel/parser';
import { getMessages } from '../src/i18n/messages.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const cyrillicPattern = /[А-Яа-яЁё]/u;
const localizationCalls = new Set(['getLocalizedText', 'getTextSync', 't', 'translate']);
const visibleAttributes = new Set(['alt', 'aria-label', 'aria-description', 'label', 'placeholder', 'title']);
const visibleObjectProperties = new Set([
  'addLabel',
  'caption',
  'description',
  'empty',
  'eyebrow',
  'helperText',
  'hint',
  'label',
  'message',
  'placeholder',
  'singular',
  'subtitle',
  'text',
  'title',
]);
const visibleCalls = new Set([
  'alert',
  'confirm',
  'confirmAction',
  'showError',
  'showInfo',
  'showSuccess',
  'showWarning',
]);
const findings = [];
const reusableKeys = new Map();
const relativeFilesExcludedFromUiAudit = new Set([
  // These two files select a complete ru/en/de data tree and are validated by check-localization.mjs.
  'content/clanWarHandbook.js',
  'content/publicDocuments.js',
  // Русский авторский справочник нового режима проверяется отдельными тестами выбора версии.
  'content/cycleClanWarHandbook.js',
  // Developer-only invariants never reach the rendered interface.
  'contexts/LocalizationContext.jsx',
  'contexts/PlayerIdentityContext.jsx',
  'services/apiFetch.js',
  // Legacy SVG-region source is not imported by the application.
  'data/mapRegions.js',
]);

Object.entries(getMessages()).forEach(([key, translations]) => {
  const russianText = String(translations?.[0] || '').replace(/\s+/g, ' ').trim();
  if (russianText && !reusableKeys.has(russianText)) reusableKeys.set(russianText, key);
});

const collectFiles = (directory) => {
  const result = [];
  readdirSync(directory).forEach((name) => {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) {
      if (name !== 'i18n') result.push(...collectFiles(path));
      return;
    }
    if (/\.(jsx?|tsx?)$/.test(name) && !/\.test\.[jt]sx?$/.test(name)) result.push(path);
  });
  return result;
};

const calleeName = (callee) => {
  if (callee?.type === 'Identifier') return callee.name;
  if (callee?.type === 'MemberExpression' && !callee.computed) return callee.property?.name || '';
  return '';
};

const attributeName = (attribute) => (
  attribute?.name?.type === 'JSXIdentifier' ? attribute.name.name : ''
);

const propertyName = (property) => {
  if (property?.key?.type === 'Identifier') return property.key.name;
  if (property?.key?.type === 'StringLiteral') return property.key.value;
  return '';
};

const compact = (value) => String(value || '').replace(/\s+/g, ' ').trim();

const report = (path, node, value) => {
  const text = compact(value);
  if (!text || !cyrillicPattern.test(text)) return;
  findings.push({
    path: relative(root, path),
    line: node.loc?.start?.line || 1,
    text,
  });
};

const visit = (path, node, visible = false) => {
  if (!node || typeof node !== 'object') return;

  if (node.type === 'CallExpression') {
    const name = calleeName(node.callee);
    if (localizationCalls.has(name)) return;
    visit(path, node.callee, false);
    node.arguments.forEach((argument) => visit(
      path,
      argument,
      visible || visibleCalls.has(name) || /Error$/.test(name),
    ));
    return;
  }

  if (node.type === 'NewExpression' && calleeName(node.callee).endsWith('Error')) {
    node.arguments.forEach((argument) => visit(path, argument, true));
    return;
  }

  if (node.type === 'ObjectProperty' || node.type === 'Property') {
    visit(path, node.value, visible || visibleObjectProperties.has(propertyName(node)));
    return;
  }

  if (
    node.type === 'VariableDeclarator'
    && node.id?.type === 'Identifier'
    && /(?:LABELS|TITLES|MESSAGES|COPY)$/.test(node.id.name)
  ) {
    visit(path, node.init, true);
    return;
  }

  if (node.type === 'JSXElement') {
    visit(path, node.openingElement, false);
    node.children.forEach((child) => visit(path, child, true));
    return;
  }

  if (node.type === 'JSXFragment') {
    node.children.forEach((child) => visit(path, child, true));
    return;
  }

  if (node.type === 'JSXOpeningElement') {
    node.attributes.forEach((attribute) => {
      const name = attributeName(attribute);
      visit(path, attribute.value, visibleAttributes.has(name));
    });
    return;
  }

  if (node.type === 'JSXExpressionContainer') {
    visit(path, node.expression, visible);
    return;
  }

  if (node.type === 'JSXText') {
    if (visible) report(path, node, node.value);
    return;
  }

  if (node.type === 'StringLiteral' || node.type === 'Literal') {
    if (visible) report(path, node, node.value);
    return;
  }

  if (node.type === 'TemplateElement') {
    if (visible) report(path, node, node.value?.cooked);
    return;
  }

  Object.entries(node).forEach(([key, value]) => {
    if (key === 'loc' || key === 'start' || key === 'end') return;
    if (Array.isArray(value)) value.forEach((child) => visit(path, child, visible));
    else if (value && typeof value === 'object') visit(path, value, visible);
  });
};

collectFiles(root).forEach((path) => {
  const relativePath = relative(root, path).replaceAll('\\', '/');
  if (relativeFilesExcludedFromUiAudit.has(relativePath)) return;
  const source = readFileSync(path, 'utf8');
  const ast = parse(source, {
    sourceType: 'module',
    plugins: ['jsx'],
    errorRecovery: false,
  });
  visit(path, ast, false);
});

if (findings.length) {
  console.error('Найдены пользовательские строки вне локализации:\n' + findings.map((item) => {
    const reusableKey = reusableKeys.get(item.text);
    return `- ${item.path}:${item.line}: ${item.text}${reusableKey ? ` [используйте ${reusableKey}]` : ''}`;
  }).join('\n'));
  process.exit(1);
}

console.log('Пользовательские строки проверены: прямой кириллический текст в UI отсутствует.');
