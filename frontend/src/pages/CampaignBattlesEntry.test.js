import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire, Module } from 'node:module';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { build } from 'esbuild';

const filename = fileURLToPath(new URL('./CampaignBattlesEntry.jsx', import.meta.url));
const bundle = await build({ entryPoints: [filename], bundle: true, write: false,
  format: 'cjs', platform: 'node', loader: { '.css': 'empty' },
  external: ['react', 'react/*', 'react-dom', 'react-dom/*', 'react-router-dom'],
  plugins: [{ name: 'entry-dependencies', setup(build) {
    build.onResolve({ filter: /useCampaignNavigation|LocalizationContext|WarsPage|components\/ui$|^@mui\/icons-material$/ },
      args => ({ path: args.path, namespace: 'entry-test' }));
    build.onLoad({ filter: /.*/, namespace: 'entry-test' }, args => ({ contents:
      args.path.includes('useCampaignNavigation')
        ? 'export default () => globalThis.__entryState;'
        : args.path.includes('LocalizationContext')
          ? 'export const useLocalizationContext = () => ({ language: globalThis.__entryLanguage });'
          : args.path.includes('WarsPage')
            ? 'import React from "react"; export default () => React.createElement("div", null, "LEGACY_WARS");'
            : args.path.includes('icons-material')
              ? 'import React from "react"; export const MilitaryTech = props => React.createElement("svg", props); export const Refresh = MilitaryTech;'
              : 'import React from "react"; export const PageShell = props => React.createElement("main", props);',
    }));
  } }], logLevel: 'silent' });
const compiled = new Module(filename, createRequire(import.meta.url));
compiled.filename = filename;
compiled.paths = Module._nodeModulePaths(fileURLToPath(new URL('../../', import.meta.url)));
compiled._compile(bundle.outputFiles[0].text, filename);
const CampaignBattlesEntry = compiled.exports.default;

function render(navigation, language = 'ru', extra = {}) {
  globalThis.__entryState = { navigation, loading: false, error: null, refresh() {}, ...extra };
  globalThis.__entryLanguage = language;
  return renderToStaticMarkup(React.createElement(MemoryRouter, null,
    React.createElement(CampaignBattlesEntry)));
}

test('interseason battle entry renders Russian archive message instead of wars or redirect', () => {
  const markup = render({ mode: 'interseason', interseason: true,
    archivedSeasonId: 1, href: '/seasons', territoryBattles: [] });
  assert.match(markup, /Межсезонье/);
  assert.match(markup, /Сезон завершён/);
  assert.match(markup, /href="\/seasons"/);
  assert.doesNotMatch(markup, /LEGACY_WARS|<button|campaign\/cycles/);
});

test('legacy responses without the new flag still render legacy battles', () => {
  assert.match(render({ mode: 'legacy', href: null, territoryBattles: [] }), /LEGACY_WARS/);
});

for (const [language, heading, label] of [
  ['en', 'Between seasons', 'Season archive'],
  ['de', 'Saisonpause', 'Saisonarchiv'],
  ['unknown', 'Межсезонье', 'Архив сезонов'],
]) {
  test(`interseason copy supports ${language} with a public archive link`, () => {
    const markup = render({ mode: 'interseason', interseason: true, href: '/seasons' }, language);
    assert.ok(markup.includes(heading));
    assert.ok(markup.includes(label));
    assert.match(markup, /href="\/seasons"/);
  });
}

test('loading and request failure retain status and retry states', () => {
  assert.match(render(null, 'ru', { loading: true }), /role="status"/);
  const error = render(null, 'ru', { error: new Error('offline') });
  assert.match(error, /role="alert"/);
  assert.match(error, /<button/);
});
