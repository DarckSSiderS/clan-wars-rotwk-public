import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire, Module } from 'node:module';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { build } from 'esbuild';

const filename = fileURLToPath(new URL('./CycleInterceptionPage.jsx', import.meta.url));
const bundle = await build({ entryPoints: [filename], bundle: true, write: false, format: 'cjs',
  platform: 'node', loader: { '.css': 'empty' }, external: ['react', 'react/*', 'react-dom', 'react-dom/*'],
  logLevel: 'silent' });
const compiled = new Module(filename, createRequire(import.meta.url));
compiled.filename = filename;
compiled.paths = Module._nodeModulePaths(fileURLToPath(new URL('../../', import.meta.url)));
compiled._compile(bundle.outputFiles[0].text, filename);
const components = compiled.exports;

const data = { revision: 3, server_time: '2026-10-20T14:06:00Z', arrives_at: '2026-10-21T00:00:00Z',
  replay_deadline: '2026-10-20T14:05:00Z', sides: [{ clan_id: 1, clan_name: 'Клан' }],
  applied_result: { outcome: 'exhausted', help_score: '200', ambush_scores: { 2: '-100' } }, audit: [] };
const common = { data, cycleId: 1, dispatchId: 'd', actorId: 9, onReload() {} };

test('форма поправки содержит причину и отдельное подтверждение без смены исхода', () => {
  assert.equal(typeof components.InterceptionReviewForm, 'function');
  const markup = renderToStaticMarkup(React.createElement(components.InterceptionReviewForm, common));
  assert.match(markup, /<textarea[^>]*required/);
  assert.match(markup, /подтверждаю|Подтверждаю/);
  assert.match(markup, /без изменения исхода/);
  assert.match(markup, /inputMode="decimal"/i);
  assert.match(markup, /disabled/);
});

test('после прибытия форма исхода не предлагает применить изменения', () => {
  assert.equal(typeof components.InterceptionOutcomeReview, 'function');
  const markup = renderToStaticMarkup(React.createElement(components.InterceptionOutcomeReview,
    { ...common, data: { ...data, server_time: data.arrives_at } }));
  assert.match(markup, /не откатываются/);
  assert.doesNotMatch(markup, /Применить исход подкрепления/);
});

test('пересмотр missingElo не подставляет текущий rating в исторический Elo', () => {
  assert.equal(typeof components.InterceptionReviewForm, 'function');
  const row = { replay_id: 'r', user_id: 7, counted: false, reason: 'missing_historical_elo',
    calculation: { historical_elo: null, rating: 951, oldRank: 665 } };
  const markup = renderToStaticMarkup(React.createElement(components.InterceptionReviewForm, { ...common, row }));
  assert.match(markup, /Исторический Elo не подтверждён/);
  assert.doesNotMatch(markup, /951|665/);
});
