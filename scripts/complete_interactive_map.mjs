import fs from 'node:fs';

const projectRoot = new URL('../', import.meta.url);
const basePath = new URL('frontend/public/map.svg', projectRoot);
const interactivePath = new URL('frontend/public/map-interactive.svg', projectRoot);

const baseSvg = fs.readFileSync(basePath, 'utf8');
const interactiveSvg = fs.readFileSync(interactivePath, 'utf8');
const pathTags = (svg) => [...svg.matchAll(/<path\b[^>]*>/g)].map(match => match[0]);
const pathData = (tag) => tag.match(/\bd="([^"]+)"/)?.[1] || '';
const startOf = (d) => d.match(/^M[-0-9.]+,[-0-9.]+/)?.[0] || '';

const missingTerritories = new Map([
  ['M1045.1,283.7', {
    name: 'Северные холмы',
    region: 'eriador',
    description: 'Северные холмы Эриадора между Арнором и землями Форохела.'
  }],
  ['M1098.1,759.2', {
    name: 'Бри',
    region: 'eriador',
    description: 'Бри и окрестные земли на перекрёстке дорог между Широм и Арнором.'
  }],
  ['M1506.9,1860.2', {
    name: 'Лебеннин',
    region: 'gondor',
    description: 'Плодородные земли южного Гондора у устья Андуина.'
  }],
  ['M1689.7,1534.9', {
    name: 'Восточный Рохан',
    region: 'rohan',
    description: 'Восточные равнины Рохана между Андуином и Белыми горами.'
  }],
  ['M2052.5,1015.9', {
    name: 'Эмин Муил',
    region: 'anduin',
    description: 'Скалистые земли у среднего течения Андуина и северных подступов к Мордору.'
  }],
  ['M1796.4,2105.1', {
    name: 'Тол-Фалас',
    region: 'gondor',
    description: 'Остров у побережья Гондора в заливе Белфалас.'
  }],
]);

const baseByStart = new Map();
for (const tag of pathTags(baseSvg)) {
  const d = pathData(tag);
  const start = startOf(d);
  if (missingTerritories.has(start) && !baseByStart.has(start)) {
    baseByStart.set(start, d);
  }
}

const existingData = new Set(pathTags(interactiveSvg).map(pathData));
const additions = [];
for (const [start, territory] of missingTerritories) {
  const d = baseByStart.get(start);
  if (!d || existingData.has(d)) continue;
  additions.push(`
                            <path class="st2 interactive-region"
                                d="${d}"
                                data-name="${territory.name}" data-region="${territory.region}"
                                data-description="${territory.description}" />`);
}

if (additions.length > 0) {
  const insertion = `${additions.join('\n')}\n`;
  const updatedSvg = interactiveSvg.replace('</g>', `${insertion}  </g>`);
  fs.writeFileSync(interactivePath, updatedSvg, 'utf8');
}

console.log(JSON.stringify({
  foundInBase: baseByStart.size,
  added: additions.length,
  totalPathTags: pathTags(interactiveSvg).length + additions.length,
  names: additions.map(addition => addition.match(/data-name="([^"]+)"/)?.[1]).filter(Boolean),
}, null, 2));
