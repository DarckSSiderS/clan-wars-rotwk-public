import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtempSync, readFileSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import process from 'node:process';
import { patchAdminPreviewEntry } from '../../../deploy/patch_admin_preview_entry.mjs';

const require = createRequire(new URL('../../package.json', import.meta.url));
const { parse } = require('@babel/parser');
const generate = require('@babel/generator').default;
const script = fileURLToPath(new URL('../../../deploy/patch_admin_preview_entry.mjs', import.meta.url));
const print = (node) => generate(node, { compact: true, comments: false }).code;
const prop = (node, name) => node.arguments?.[1]?.properties?.find(
  (entry) => (entry.key?.name ?? entry.key?.value) === name,
)?.value;

function calls(node, predicate) {
  if (!node || typeof node !== 'object') return [];
  const found = node.type === 'CallExpression' && predicate(node) ? [node] : [];
  return found.concat(Object.values(node).flatMap((value) => (
    Array.isArray(value) ? value.flatMap((entry) => calls(entry, predicate)) : calls(value, predicate)
  )));
}

const sidebar = 'r.jsxs(P,{component:"aside",className:"admin-sidebar",children:[r.jsx(B,{className:"admin-sidebar__logo"}),r.jsxs(B,{className:"admin-sidebar__campaign",children:["Campaign",season]}),r.jsxs(T,{className:"admin-tabs",children:[r.jsx(U,{value:0,icon:r.jsx(A,{})}),r.jsx(U,{value:12,icon:r.jsx(S,{})})]}),r.jsx(B,{className:"admin-sidebar__footer"})]})';
const fixture = `import{j as r,P,B,T,U,S,A}from"./shared-OLD.js";import"./AdminDashboardPage-OLD.css";const season="old mechanics";export const page=()=>${sidebar};export const untouched=()=>r.jsx(B,{children:"legacy"});`;

test('patches only the sidebar entry, reuses runtime and unique icon, preserves imports and old mechanics', () => {
  const patched = patchAdminPreviewEntry(fixture);
  const ast = parse(patched, { sourceType: 'module' });
  const sidebars = calls(ast, (node) => prop(node, 'className')?.value === 'admin-sidebar');
  assert.equal(sidebars.length, 1);
  const children = prop(sidebars[0], 'children').elements;
  assert.equal(children.length, 5);
  const link = children[2];
  assert.equal(link.arguments[0].value, 'a');
  assert.equal(print(link.callee), 'r.jsxs');
  assert.equal(prop(link, 'href').value, '/admin/preview/');
  assert.equal(prop(link, 'className').value, 'admin-sidebar__preview');
  assert.equal(prop(link, 'style'), undefined);
  const contents = prop(link, 'children').elements;
  assert.equal(print(contents[0]), 'r.jsx(S,{})');
  assert.equal(contents[1].value, 'Предпросмотр новой версии');
  assert.equal(prop(children[1], 'className').value, 'admin-sidebar__campaign');
  assert.equal(prop(children[3], 'className').value, 'admin-tabs');
  assert.throws(() => patchAdminPreviewEntry(patched), /already|duplicate/i);
  children.splice(2, 1);
  assert.equal(print(ast), print(parse(fixture, { sourceType: 'module' })));
});

test('fails closed on missing or ambiguous structure and omits absent, ambiguous or unsafe icons', () => {
  const variants = [
    fixture.replace('value:12', 'value:11'),
    fixture.replace('value:0', 'value:12'),
    fixture.replace('icon:r.jsx(S,{})', 'icon:makeIcon()'),
    fixture.replace('icon:r.jsx(S,{})', 'icon:r.jsx(getIcon(),{})'),
    fixture.replace('icon:r.jsx(S,{})', 'icon:r.jsx(S,{}),icon:r.jsx(A,{})'),
    fixture.replace('icon:r.jsx(S,{})', 'icon:r.jsx(S,{}),...tabOverrides'),
    fixture.replace('icon:r.jsx(S,{})', 'icon:r.jsx(S,{titleAccess:makeTitle()})'),
  ];
  for (const source of variants) {
    const patched = parse(patchAdminPreviewEntry(source), { sourceType: 'module' });
    const [link] = calls(patched, (node) => prop(node, 'href')?.value === '/admin/preview/');
    assert.ok(link, 'entry remains available without a safe unique icon');
    assert.equal(prop(link, 'children').type, 'StringLiteral');
    assert.equal(prop(link, 'children').value, 'Предпросмотр новой версии');
  }
  const identifierRuntime = fixture.replaceAll('r.jsxs', 'z').replaceAll('r.jsx', 'q');
  const ast = parse(patchAdminPreviewEntry(identifierRuntime), { sourceType: 'module' });
  const [link] = calls(ast, (node) => prop(node, 'href')?.value === '/admin/preview/');
  assert.equal(print(link.callee), 'z');
  const invalid = [
    [fixture.replace('"admin-sidebar"', '"not-sidebar"'), /sidebar/i],
    [`${fixture};const duplicate=${sidebar};`, /sidebar/i],
    ['r.jsx(P,{className:"admin-sidebar",children:items})', /children|array/i],
    [fixture.replace('"admin-sidebar__campaign"', '"other"'), /campaign/i],
    [fixture.replace('"admin-sidebar__logo"', '"admin-sidebar__campaign"'), /campaign/i],
    [fixture.replace('className:"admin-sidebar__logo"', 'href:"/admin/preview/"'), /already|duplicate/i],
  ];
  for (const [source, error] of invalid) assert.throws(() => patchAdminPreviewEntry(source), error);
});

test('CLI writes a separate asset, never overwrites input or existing output, and writes nothing on refusal', () => {
  const directory = mkdtempSync(join(tmpdir(), 'admin-preview-entry-'));
  const input = join(directory, 'AdminDashboardPage-old.js');
  const output = join(directory, 'AdminDashboardPage-patched.js');
  const rejected = join(directory, 'rejected.js');
  const run = (...args) => spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' });
  try {
    writeFileSync(input, fixture);
    const result = run(input, output);
    assert.equal(result.status, 0, result.stderr);
    assert.ok(existsSync(output), 'CLI must create the patched asset');
    assert.equal(readFileSync(input, 'utf8'), fixture);
    assert.equal(readFileSync(output, 'utf8'), patchAdminPreviewEntry(fixture));
    assert.notEqual(run(input, input).status, 0);
    assert.notEqual(run(input, join(directory, '.', 'AdminDashboardPage-old.js')).status, 0);
    assert.notEqual(run(input, output).status, 0);
    assert.equal(readFileSync(input, 'utf8'), fixture);
    assert.equal(readFileSync(output, 'utf8'), patchAdminPreviewEntry(fixture));
    writeFileSync(input, 'export const legacy = true;');
    const refusal = run(input, rejected);
    assert.notEqual(refusal.status, 0);
    assert.match(refusal.stderr, /sidebar/i);
    assert.equal(existsSync(rejected), false);
    assert.notEqual(run().status, 0);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
