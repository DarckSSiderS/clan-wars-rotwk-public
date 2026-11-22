import { test, expect } from '@playwright/test';

const clans = [
  { id: 7, name: 'Наш клан', leader_id: 1, member_count: 4, territory_count: 0, territory_points: 0 },
  { id: 8, name: 'Соседний клан', leader_id: 2, member_count: 4, territory_count: 0, territory_points: 0 },
];
const old = { id: 12, status: 'pending_alliance', clan_low: { id: 7, name: 'Старый тестовый клан' }, clan_high: clans[1] };
async function setup(page, { mode='interseason', currentError=false, language='ru', guest=false, cycleError=false }={}) {
  const requests=[];
  await page.addInitScript(lang=>localStorage.setItem('language',lang),language);
  await page.route('**/api/v1/**', async route=>{
    const path=new URL(route.request().url()).pathname;
    requests.push(path);
    let payload={};
    if (path.endsWith('/auth/session') || path.endsWith('/users/me')) {
      if(guest) return route.fulfill({status:401,json:{detail:'Unauthorized'}});
      payload={id:1,username:'Head',language,role:{name:'user'},onboarding_completed:true,is_claimed:true,is_verified:true};
    } else if(path==='/api/v1/clans/')payload=clans;
    else if(path.endsWith('/clans/my'))payload=clans[0];
    else if(path.endsWith('/campaign/cycles/current')) {
      if(currentError)return route.fulfill({status:503,json:{detail:'Unavailable'}});
      payload={mechanics_version:mode==='cycle_v1'?'cycle_v1':'legacy',interseason:mode==='interseason',archived_season_id:1,
        cycle:mode==='cycle_v1'?{id:9}:null,territory_battles:[]};
    } else if(path.endsWith('/clans/diplomacy'))payload=[old];
    else if(path.endsWith('/diplomacy/cycles/9')) {
      if(cycleError)return route.fulfill({status:503,json:{detail:'Unavailable'}});
      payload={relations:[{clan_low_id:7,clan_high_id:8,clan_low:clans[0],clan_high:clans[1],status:'allied'}]};
    } else if(path==='/api/v1/wars/')payload=[{id:1,status:'active',defending_clan_id:8,territory_name:'Старая тестовая битва'}];
    else if(path.includes('localization'))payload=[];
    else if(path.includes('notifications'))payload={items:[],unread_count:0,total:0};
    return route.fulfill({json:payload});
  });
  await page.goto('/clans');
  if(guest)await expect(page.getByRole('dialog')).toBeVisible();
  else await expect(page.locator('[data-section="alliances"]')).toBeVisible();
  return requests;
}

test('interseason clan diplomacy never exposes old proposals, battles or legacy management',async({page})=>{
  const requests=await setup(page);
  const section=page.locator('[data-section="alliances"]');
  await expect(section).toContainText('Новый сезон ещё не запущен');
  await expect(section).not.toContainText('Старый тестовый клан');
  await expect(section).not.toContainText('Старая тестовая битва');
  await expect(section.getByRole('button',{name:'Управление',exact:true})).toHaveCount(0);
  expect(requests.some(path=>path.endsWith('/clans/diplomacy'))).toBe(false);
  await page.screenshot({path:'test-results/clans-diplomacy-interseason.png',fullPage:true});
});

test('active campaign summary uses only its cycle relations and opens current diplomacy',async({page})=>{
  const requests=await setup(page,{mode:'cycle_v1'});
  const section=page.locator('[data-section="alliances"]');
  await expect(section).toContainText('Союз');
  await expect(section).toContainText('Соседний клан');
  await expect(section).not.toContainText('Старый тестовый клан');
  await expect(section).not.toContainText('Старая тестовая битва');
  await expect(section.getByRole('link',{name:/дипломати/})).toHaveAttribute('href','/campaign/cycles/9/diplomacy');
  expect(requests.some(path=>path.endsWith('/clans/diplomacy'))).toBe(false);
});

for(const options of [{currentError:true},{mode:'cycle_v1',cycleError:true}])test(`failed campaign or relations read never falls back to old diplomacy ${JSON.stringify(options)}`,async({page})=>{
  const requests=await setup(page,options);
  const section=page.locator('[data-section="alliances"]');
  await expect(section.getByRole('alert')).toBeVisible();
  await expect(section).not.toContainText('Старый тестовый клан');
  expect(requests.some(path=>path.endsWith('/clans/diplomacy'))).toBe(false);
});

test('an active legacy campaign keeps its existing diplomacy',async({page})=>{
  await setup(page,{mode:'legacy'});
  await expect(page.locator('[data-section="alliances"]')).toContainText('Старый тестовый клан');
});

test('guest clan catalogue does not request private campaign or diplomatic data',async({page})=>{
  const requests=await setup(page,{guest:true});
  await expect(page.getByRole('dialog')).toContainText('Войдите');
  await expect(page.locator('[data-section="alliances"]')).toHaveCount(0);
  expect(requests.some(path=>path.endsWith('/clans/diplomacy') || path.endsWith('/campaign/cycles/current'))).toBe(false);
});

for(const [language,copy] of [['en','The new season has not started'],['de','Die neue Saison hat noch nicht begonnen']])test(`interseason state is localized in ${language}`,async({page})=>{
  await setup(page,{language});
  await expect(page.locator('[data-section="alliances"]')).toContainText(copy);
});
