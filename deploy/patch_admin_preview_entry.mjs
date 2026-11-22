import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const { parse } = require('@babel/parser');
const generate = require('@babel/generator').default;
const types = require('@babel/types');

const PREVIEW_URL = '/admin/preview/';
const PREVIEW_CLASS = 'admin-sidebar__preview';
const PREVIEW_LABEL = '\u041f\u0440\u0435\u0434\u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440 \u043d\u043e\u0432\u043e\u0439 \u0432\u0435\u0440\u0441\u0438\u0438';

function visit(node, callback) {
  if (!node || typeof node !== 'object' || !node.type) return;
  callback(node);
  for (const key of types.VISITOR_KEYS[node.type] || []) {
    const children = node[key];
    if (Array.isArray(children)) children.forEach((child) => visit(child, callback));
    else visit(children, callback);
  }
}

function propsOf(node) {
  return types.isCallExpression(node) && types.isObjectExpression(node.arguments[1])
    ? node.arguments[1] : null;
}

function property(props, name) {
  const matches = props?.properties.filter((entry) => types.isObjectProperty(entry)
    && !entry.computed && (entry.key.name ?? entry.key.value) === name) || [];
  if (matches.length > 1) throw new Error(`Ambiguous property: ${name}`);
  return matches[0]?.value;
}

function hasClass(node, name) {
  return types.isStringLiteral(property(propsOf(node), 'className'), { value: name });
}

function isRuntimeCallee(node) {
  return types.isIdentifier(node) || (types.isMemberExpression(node) && !node.computed
    && types.isIdentifier(node.object) && ['jsx', 'jsxs'].includes(node.property.name));
}

function uniqueTabIcon(children) {
  const tabs = children.filter((child) => hasClass(child, 'admin-tabs'));
  if (tabs.length !== 1) return null;
  const items = property(propsOf(tabs[0]), 'children');
  if (!types.isArrayExpression(items)) return null;
  for (const item of items.elements) {
    const props = propsOf(item);
    if (!props) return null;
    const names = new Set();
    for (const entry of props.properties) {
      if (!types.isObjectProperty(entry) || entry.computed) return null;
      const name = entry.key.name ?? entry.key.value;
      if (names.has(name)) return null;
      names.add(name);
    }
  }
  const matches = items.elements.filter((item) => types.isNumericLiteral(
    property(propsOf(item), 'value'), { value: 12 },
  ));
  if (matches.length !== 1) return null;
  const tab = matches[0];
  const icon = property(propsOf(tab), 'icon');
  // Only clone a plain runtime element: no factories, spreads or scoped expressions.
  if (!types.isCallExpression(icon) || icon.arguments.length !== 2
    || !types.isIdentifier(icon.arguments[0]) || !isRuntimeCallee(icon.callee)
    || !types.isNodesEquivalent(icon.callee, tab.callee)
    || !types.isObjectExpression(icon.arguments[1]) || icon.arguments[1].properties.length) return null;
  return types.cloneNode(icon, true);
}

export function patchAdminPreviewEntry(source) {
  const ast = parse(source, { sourceType: 'module' });
  const sidebars = [];
  visit(ast, (node) => {
    if (hasClass(node, 'admin-sidebar')) sidebars.push(node);
  });
  if (sidebars.length !== 1) {
    throw new Error(`Expected exactly one admin-sidebar runtime call; found ${sidebars.length}`);
  }
  const sidebar = sidebars[0];
  const props = propsOf(sidebar);
  const children = property(props, 'children');
  if (!isRuntimeCallee(sidebar.callee) || props.properties.some((entry) => types.isSpreadElement(entry))) {
    throw new Error('Unsupported admin-sidebar runtime or spread props');
  }
  if (!types.isArrayExpression(children)) throw new Error('admin-sidebar children must be an array');
  visit(sidebar, (node) => {
    if (types.isStringLiteral(property(propsOf(node), 'href'), { value: PREVIEW_URL })
      || hasClass(node, PREVIEW_CLASS)) throw new Error('Preview entry already exists; refusing duplicate insertion');
  });
  const campaignIndexes = children.elements.flatMap((child, index) => (
    hasClass(child, 'admin-sidebar__campaign') ? [index] : []
  ));
  if (campaignIndexes.length !== 1) {
    throw new Error(`Expected exactly one direct admin-sidebar__campaign; found ${campaignIndexes.length}`);
  }
  const icon = uniqueTabIcon(children.elements);
  const label = types.stringLiteral(PREVIEW_LABEL);
  const link = types.callExpression(types.cloneNode(sidebar.callee, true), [
    types.stringLiteral('a'),
    types.objectExpression([
      types.objectProperty(types.identifier('className'), types.stringLiteral(PREVIEW_CLASS)),
      types.objectProperty(types.identifier('href'), types.stringLiteral(PREVIEW_URL)),
      types.objectProperty(types.identifier('children'), icon ? types.arrayExpression([icon, label]) : label),
    ]),
  ]);
  children.elements.splice(campaignIndexes[0] + 1, 0, link);
  return `${generate(ast, { compact: true, minified: true, comments: true }).code}\n`;
}

async function main(args) {
  if (args.length !== 2) throw new Error('Usage: node deploy/patch_admin_preview_entry.mjs <input-admin.js> <output-admin.js>');
  const [input, output] = args.map((path) => resolve(path));
  if (input === output) throw new Error('Input and output must be different files');
  const patched = patchAdminPreviewEntry(await readFile(input, 'utf8'));
  // Exclusive creation also rejects existing symlinks/hardlinks back to the input.
  await writeFile(output, patched, { encoding: 'utf8', flag: 'wx' });
  process.stdout.write(`Patched one admin sidebar: ${output}\n`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
